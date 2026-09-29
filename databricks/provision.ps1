# Phase 6 — provisions the Azure Databricks side of the lakehouse and deploys the Bronze pipeline.
# Records the exact steps used to build what's running, so it can be rebuilt from scratch.
#
# PowerShell, not bash: Azure CLI's DNS resolution is broken in this machine's Git Bash, and the
# Databricks CLI needs JSON files written without a BOM (Out-File adds one; WriteAllText doesn't).
#
# Prereqs: `az login` done; Databricks CLI installed (winget install Databricks.DatabricksCLI);
# the Kafka VM (ekadai-vm, NSG ekadai-vm-nsg) already running — see azure/vm-stack/.
# Run from the repo root: powershell -File databricks/provision.ps1

$ErrorActionPreference = "Stop"
$RG = "ekadai-rg"
$LOCATION = "eastus"
$STORAGE = "ekadailake"
$WORKSPACE = "ekadai-databricks"
$CONNECTOR = "ekadai-access-connector"
$CATALOG = "ekadai_databricks"   # auto-created default catalog for this workspace
$NSG = "ekadai-vm-nsg"

function Write-Json($path, $obj) {
    [System.IO.File]::WriteAllText($path, ($obj | ConvertTo-Json -Depth 10))
}

# --- Azure resources -------------------------------------------------------------------------
az provider register --namespace Microsoft.Databricks --wait

# ADLS Gen2 (hierarchical namespace) with one container per lakehouse layer.
az storage account create -g $RG -n $STORAGE -l $LOCATION --sku Standard_LRS --kind StorageV2 --hns true | Out-Null
$key = az storage account keys list -g $RG --account-name $STORAGE --query "[0].value" -o tsv
foreach ($c in "bronze", "silver", "gold") {
    az storage container create --account-name $STORAGE --account-key $key -n $c | Out-Null
}

# Premium is the only SKU Azure accepts for new workspaces (Standard is deprecated).
az extension add --name databricks --yes
az databricks workspace create -g $RG -n $WORKSPACE -l $LOCATION --sku premium | Out-Null

# Managed identity Unity Catalog uses to read/write the storage account.
az databricks access-connector create -g $RG -n $CONNECTOR -l $LOCATION --identity-type SystemAssigned | Out-Null
$principal = az databricks access-connector show -g $RG -n $CONNECTOR --query identity.principalId -o tsv
$storageId = az storage account show -g $RG -n $STORAGE --query id -o tsv
az role assignment create --assignee-object-id $principal --assignee-principal-type ServicePrincipal `
    --role "Storage Blob Data Contributor" --scope $storageId | Out-Null

# Serverless compute doesn't run in the workspace VNet, so it needs its own path to Kafka and
# Schema Registry. The regional service tag is maintained by Azure as the egress pool changes —
# pinning individual IPs breaks (observed egress IP changed between two probe runs).
az network nsg rule create -g $RG --nsg-name $NSG -n allow-databricks-serverless-kafka --priority 130 `
    --access Allow --protocol Tcp --direction Inbound `
    --source-address-prefixes AzureDatabricksServerless.EastUS --source-port-ranges "*" `
    --destination-port-ranges 29092 8081 | Out-Null

# --- Unity Catalog ----------------------------------------------------------------------------
$env:DATABRICKS_HOST = "https://" + (az databricks workspace show -g $RG -n $WORKSPACE --query workspaceUrl -o tsv)
$env:DATABRICKS_AZURE_RESOURCE_ID = az databricks workspace show -g $RG -n $WORKSPACE --query id -o tsv
$connectorId = az databricks access-connector show -g $RG -n $CONNECTOR --query id -o tsv

Write-Json "$env:TEMP\uc_cred.json" @{ name = "ekadai-storage-credential"; azure_managed_identity = @{ access_connector_id = $connectorId } }
databricks storage-credentials create --json "@$env:TEMP\uc_cred.json" | Out-Null

foreach ($layer in "bronze", "silver", "gold") {
    $url = "abfss://$layer@$STORAGE.dfs.core.windows.net/"
    Write-Json "$env:TEMP\uc_loc.json" @{ name = "ekadai-$layer"; url = $url; credential_name = "ekadai-storage-credential" }
    databricks external-locations create --json "@$env:TEMP\uc_loc.json" | Out-Null
    Write-Json "$env:TEMP\uc_schema.json" @{ name = $layer; catalog_name = $CATALOG; storage_root = $url }
    databricks schemas create --json "@$env:TEMP\uc_schema.json" | Out-Null
}
# Observability area (§97) — kept apart from the Gold business tables, stored under the gold
# container's ops/ prefix (already covered by the ekadai-gold external location).
Write-Json "$env:TEMP\uc_schema.json" @{ name = "ops"; catalog_name = $CATALOG; storage_root = "abfss://gold@$STORAGE.dfs.core.windows.net/ops/" }
databricks schemas create --json "@$env:TEMP\uc_schema.json" | Out-Null

# --- Lakehouse pipeline (serverless, continuous): Bronze (Phase 6) + Silver events (Phase 7) ---
# One pipeline, one always-on compute. Bronze tables publish to the default `bronze` schema;
# silver_pipeline.py publishes fully-qualified into `$CATALOG.silver`.
databricks workspace mkdirs /Workspace/ekadai
foreach ($src in "bronze_pipeline", "silver_pipeline", "silver_cdc_pipeline", "gold_pipeline") {
    databricks workspace import "/Workspace/ekadai/$src.py" --file "databricks/$src.py" `
        --language PYTHON --format SOURCE --overwrite
}
# silver_rules.py is imported by silver_pipeline.py, so it must be a plain workspace FILE
# (format AUTO), not a notebook — notebooks aren't importable as Python modules.
databricks workspace import /Workspace/ekadai/silver_rules.py --file databricks/silver_rules.py `
    --format AUTO --overwrite

$PIPELINE_VERSION = "1.1.0"   # §43 — bump on every pipeline code change
Write-Json "$env:TEMP\pipeline.json" @{
    name          = "ekadai-bronze"
    serverless    = $true
    # Continuous = real time, but bills around the clock. While building on a fixed credit
    # budget it runs triggered (each update processes everything new, then stops); flip to
    # $true for live operation/demos.
    continuous    = $false
    # §97/§99: the pipeline's own event log (runs, flow progress, row counts, backlog, errors)
    # published as a table, which the ops views are built on.
    event_log     = @{ catalog = $CATALOG; schema = "ops"; name = "pipeline_event_log" }
    development   = $false
    catalog       = $CATALOG
    schema        = "bronze"
    channel       = "CURRENT"
    # §65 lateness thresholds (Phase 10) — tune here, no code change needed.
    configuration = @{
        "ekadai.pipeline_version"         = $PIPELINE_VERSION
        "ekadai.watermark_minutes"        = "10"
        "ekadai.allowed_lateness_minutes" = "5"
    }
    libraries     = @(
        @{ notebook = @{ path = "/Workspace/ekadai/bronze_pipeline.py" } },
        @{ notebook = @{ path = "/Workspace/ekadai/silver_pipeline.py" } },
        @{ notebook = @{ path = "/Workspace/ekadai/silver_cdc_pipeline.py" } },
        @{ notebook = @{ path = "/Workspace/ekadai/gold_pipeline.py" } }
    )
    environment   = @{ dependencies = @("fastavro") }
}
databricks pipelines create --json "@$env:TEMP\pipeline.json"
# Updating an existing pipeline instead: `databricks pipelines update <id> --json @...` REPLACES
# the whole spec (include pipeline_id + every field). A change to a table's columns (e.g. the
# Phase 7 raw_value/decode_error columns) needs `databricks pipelines start-update <id>
# --full-refresh`; confirm the update's `full_refresh: true` — a settings edit alone restarts
# the pipeline WITHOUT a full refresh.
# Refreshing ONE table (e.g. silver_events after its source changes): `full_refresh_selection` is
# rejected in continuous mode — temporarily set `continuous: false`, run
# `start-update --json '{"full_refresh_selection":["ekadai_databricks.silver.silver_events"]}'`,
# wait for COMPLETED, then set `continuous: true` again (that restarts it).
# ⚠ A full refresh of BRONZE re-reads Kafka from `earliest`; Kafka keeps 7 days, so once the
# initial Debezium snapshot (2026-09-26) ages out, a Bronze full refresh would lose it.

# --- Spec-shaped SCD2 views (Phase 8) ---------------------------------------------------------
# Run once the pipeline has created the *_history tables. Needs a SQL warehouse id.
$WAREHOUSE_ID = databricks warehouses list -o json | ConvertFrom-Json | Select-Object -First 1 -ExpandProperty id
# silver_views.sql (Phase 8 SCD2 views) and ops_views.sql (Phase 13 observability views; needs
# the event log table, i.e. at least one pipeline update first).
$views = foreach ($file in "databricks/silver_views.sql", "databricks/ops_views.sql") {
    (Get-Content -Raw $file) -split "(?m)^;\s*$" |
        ForEach-Object { ($_ -split "`n" | Where-Object { $_ -notmatch '^\s*--' }) -join "`n" } |
        Where-Object { $_.Trim() }
}
foreach ($stmt in $views) {
    Write-Json "$env:TEMP\stmt.json" @{ warehouse_id = $WAREHOUSE_ID; statement = $stmt.Trim(); wait_timeout = "50s" }
    databricks api post /api/2.0/sql/statements --json "@$env:TEMP\stmt.json" | Out-Null
}
# SQL warehouse: auto-stop at the 1-minute minimum — the Airflow DAGs wake it hourly, and a
# 10-minute idle tail per run would bill for far more than the queries take.
#   databricks warehouses edit <id> --json '{..., "auto_stop_mins": 1}'
#
# Airflow (Phase 10) runs on the VM — see azure/vm-stack/airflow/. It needs a Databricks token:
#   databricks tokens create --lifetime-seconds 1209600 --comment "airflow on ekadai-vm"
# written ONLY into azure/vm-stack/airflow/airflow.env on the VM (chmod 600, gitignored) as
#   AIRFLOW_CONN_DATABRICKS_DEFAULT={"conn_type":"databricks","host":"https://<workspace>","password":"<token>"}
# plus NSG rule allow-airflow-ui (TCP 8080, dev IP only, priority 140).
#
# Supabase side of Phase 8: `python -m debezium.setup_postgres` sets REPLICA IDENTITY FULL on the
# 5 CDC tables so UPDATE/DELETE events carry the full before image (§46, status_before in §69).

Write-Output "Done. Continuous pipelines bill while running — stop between sessions with:"
Write-Output "  databricks pipelines stop <pipeline_id>"
