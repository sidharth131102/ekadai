# Ekadai

A working e-commerce store plus the **real-time data platform** behind it:
- **FastAPI + React** app on **PostgreSQL (Supabase)**;
- **Avro behavioral events** and **Debezium CDC** into **Kafka** (KRaft + Schema Registry, on an
  Azure VM);
- an **Azure Databricks** lakehouse, Bronze → Silver → Gold (one serverless Lakeflow
  pipeline, Unity Catalog);
- **Airflow** for replay, backfill, health and maintenance;
- **Power BI** on Gold and on an ops/observability schema.

A click on the storefront reaches Silver in about **13 s** and the Gold dashboards in about
**1.5 min** when the pipeline runs continuously.

```
Browser (Vercel) ─► Caddy/HTTPS ─► FastAPI ─┬─► Postgres (Supabase) ─► Debezium ─┐
                                            └─► Avro events ──────────────────────┴─► Kafka
Kafka ─► Databricks Lakeflow: Bronze ─► Silver ─► Gold ─► Power BI
                                    └─► ops (event log, quality, lag, queues) ─► Power BI
Airflow (VM): late-data replay · Kafka/CDC health · backfill + reconciliation · maintenance
```

**Live** (when the cloud stack is switched on, see Cost):
- storefront: https://ekadai-rouge.vercel.app
- API: https://ekadai-api.eastus.cloudapp.azure.com

## Documentation

| Doc | What's in it |
|---|---|
| [docs/PROJECT_DEEP_DIVE.md](docs/PROJECT_DEEP_DIVE.md) | **Start here to explain the project**: services and why, data flow, data models, business rules, key queries, optimisations, guarantees, verification, trade-offs, likely questions |
| [docs/architecture.md](docs/architecture.md) | Architecture by layer (§110), cost, deployment, design trade-offs |
| [docs/failure_testing.md](docs/failure_testing.md) | Failure/recovery scenario matrix and recorded results (§107) |
| [docs/powerbi.md](docs/powerbi.md) | Opening the generated Power BI project; model, measures, pages; live (DirectQuery) mode |
| [MASTER_BUILD_PROMPT.md](MASTER_BUILD_PROMPT.md) | The authoritative architecture contract (§ references point here) |
| [roadmap.md](roadmap.md) · [current_state.md](current_state.md) · [bugs_and_fixes.md](bugs_and_fixes.md) | Phase status, detailed build log, issue log |

## Status

| Phases | State |
|---|---|
| 1–10: schema, app, event contracts, Kafka, CDC, Bronze, Silver, SCD2, reference resolution, late data | Built and verified live |
| 11–12: Gold dimensions, facts, aggregates | Built and verified on live data (reconciled counts and totals) |
| 13: observability | Built; views created; DAGs deployed; health DAG run. `backfill_reconcile` / `lakehouse_maintenance` not yet triggered |
| 14: Power BI | Generated project working in Import and DirectQuery mode |
| 15: failure testing | Most scenarios verified live; the outage/restart ones are still to run (see the matrix) |
| 16: docs + deployment | Done: storefront on Vercel, API on the VM behind HTTPS |

## Repository layout

| Path | What |
|---|---|
| `app/` | FastAPI backend (auth, catalog, cart, wishlist, checkout, orders, reviews, `POST /events`) |
| `web/` | React + Vite + TypeScript storefront (`vercel.json` for SPA routing) |
| `db/` | SQLAlchemy models (13 tables), Alembic migrations, seed data |
| `events/` | 18 Avro contracts, producer, transports (logging / Kafka + Avro) |
| `kafka/`, `debezium/` | Topic/schema/connector registration; local Docker Compose versions |
| `azure/vm-stack/` | VM stack: Kafka, Schema Registry, Debezium (`docker-compose.yml`); `api/` (FastAPI + Caddy); `airflow/` (image + 4 DAGs) |
| `databricks/` | Pipeline sources (`bronze_`, `silver_`, `silver_cdc_`, `gold_pipeline.py`), `silver_rules.py`, `silver_views.sql`, `ops_views.sql`, `provision.ps1` |
| `powerbi/` | `generate_pbip.py` + the generated PBIP project (`ekadai.pbip`) |
| `scripts/` | Bootstrap, `simulate_traffic.py` (labelled `sim-` shoppers through the real API), `failure_tests.py` |
| `tests/` | pytest: DB constraints, API, events, Silver validation rules (203 passed, 2 skipped) |

## Local development

Requires Docker Desktop, Python 3.12+ and Node 20+.

```bash
cp .env.example .env                  # EVENT_TRANSPORT=logging needs no Kafka
pip install -r requirements.txt
scripts/bootstrap.sh                  # or scripts/bootstrap.ps1: Postgres, migrations, seed
pytest tests/ -q                      # 203 passed, 2 skipped
uvicorn app.main:app --reload         # http://localhost:8000/docs
cd web && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

The local Kafka + Debezium stack (`kafka/docker-compose.yml`, `debezium/docker-compose.yml`)
gives you the event and CDC path without the cloud.

## Cloud deployment

1. **Postgres (Supabase)**: `alembic -c db/alembic.ini upgrade head`,
   `python db/seed/run_seed.py`, `python -m debezium.setup_postgres` (Debezium role, table
   ownership, `REPLICA IDENTITY FULL`).
2. **VM streaming stack**: `azure/vm-stack/docker-compose.yml`, then
   `kafka/create_topics.py`, `kafka/register_schemas.py`, `debezium/register_connector.py`.
3. **Databricks**: `databricks/provision.ps1` (storage, workspace, Unity Catalog, NSG
   service-tag rule, pipeline with the event log, Silver/ops views).
4. **Airflow**: `azure/vm-stack/airflow/` with a Databricks token in the VM-only `airflow.env`.
5. **API**: `azure/vm-stack/api/`, FastAPI + Caddy (automatic HTTPS for the VM's Azure DNS
   name), secrets in the VM-only `api.env`.
6. **Storefront**: `cd web && vercel deploy --prod --build-env VITE_API_BASE_URL=https://<api-domain>`,
   then add the Vercel domain to `CORS_ORIGINS` in `api.env`.
7. **Power BI**:
   `python powerbi/generate_pbip.py --columns powerbi/columns.txt [--mode directquery]`,
   then open `powerbi/ekadai.pbip` (see [docs/powerbi.md](docs/powerbi.md)).

## Cost

- The pipeline normally runs **triggered**: each update catches up from Kafka, then stops.
  Switch it to `continuous` for live real-time demos.
- The SQL warehouse auto-stops after 1 minute.
- The VM can be deallocated between sessions; its IP is static.
- Details: [docs/architecture.md §18](docs/architecture.md#18-cost).

Secrets never go into git: `.env`, `azure/vm-stack/api/api.env` and
`azure/vm-stack/airflow/airflow.env` are gitignored.
