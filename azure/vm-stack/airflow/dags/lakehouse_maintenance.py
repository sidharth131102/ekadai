"""Daily lakehouse maintenance (§95 retention; §61 "Airflow is for maintenance").

- Retention for the tables Airflow owns: ops health samples (30 days); the late replay queue's
  PROCESSED rows are pruned by the late_data_replay DAG itself (processed + 30 days).
- OPTIMIZE + VACUUM (default 7-day retention) on those externally-written Delta tables.
- Retention check for the pipeline-managed tables (Bronze 90d, Silver 90d, quarantine 30d):
  those tables are owned by the pipeline and can't be edited from outside it, so this task
  *reports* them via ops.retention_status and fails loudly if any is overdue, rather than
  deleting underneath the streams (a DELETE on a streaming source would break its readers).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.hooks.sql import fetch_all_handler
from airflow.providers.databricks.hooks.databricks_sql import DatabricksSqlHook
from airflow.providers.databricks.operators.databricks_sql import DatabricksSqlOperator

HTTP_PATH = os.environ.get("EKADAI_SQL_WAREHOUSE_HTTP_PATH")
C = "ekadai_databricks"
OWNED = [f"{C}.ops.kafka_offsets", f"{C}.ops.cdc_connector_status", f"{C}.silver.late_data_replay_queue"]

PRUNE = [
    f"DELETE FROM {C}.ops.kafka_offsets WHERE captured_at < current_timestamp() - INTERVAL 30 DAYS",
    f"DELETE FROM {C}.ops.cdc_connector_status WHERE captured_at < current_timestamp() - INTERVAL 30 DAYS",
]
COMPACT = [s for t in OWNED for s in (f"OPTIMIZE {t}", f"VACUUM {t}")]


def check_retention(**_):
    hook = DatabricksSqlHook(databricks_conn_id="databricks_default", http_path=HTTP_PATH)
    rows = hook.run(f"SELECT table_name, retention_days, oldest_age_days, overdue FROM {C}.ops.retention_status",
                    handler=fetch_all_handler)
    for name, days, age, overdue in rows:
        print(f"{'OVERDUE' if overdue else 'ok':8} {name}: oldest {age} days (policy {days})")
    overdue = [r[0] for r in rows if r[3]]
    if overdue:
        raise RuntimeError(f"retention overdue for: {overdue}")


common = {"databricks_conn_id": "databricks_default", "http_path": HTTP_PATH}

with DAG(
    dag_id="lakehouse_maintenance",
    description="Retention pruning, OPTIMIZE/VACUUM, retention checks (§95).",
    start_date=datetime(2026, 9, 29),
    schedule="0 3 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["ekadai", "maintenance"],
) as dag:
    prune = DatabricksSqlOperator(task_id="prune_ops_samples", sql=PRUNE, **common)
    compact = DatabricksSqlOperator(task_id="optimize_vacuum", sql=COMPACT, **common)
    check = PythonOperator(task_id="check_retention", python_callable=check_retention)
    prune >> compact >> check
