# Ekadai

A real e-commerce application plus the real-time data platform behind it:
- **FastAPI + React** app on **PostgreSQL (Supabase)**;
- **Avro behavioral events** and **Debezium CDC** into **Kafka** (KRaft + Schema Registry, on an
  Azure VM);
- an **Azure Databricks** lakehouse, Bronze → Silver → Gold (one serverless Lakeflow
  pipeline, Unity Catalog);
- **Airflow** for replay, backfill and maintenance;
- **Power BI** on Gold.

```
React ─► FastAPI ─► Postgres (Supabase) ─► Debezium ─┐
           └──────── Avro events ────────────────────┴─► Kafka ─► Bronze ─► Silver ─► Gold ─► Power BI
                                                                                 └► ops ─► Power BI
```

## Documentation

- [docs/architecture.md](docs/architecture.md): architecture, every layer, cost and trade-offs
  (§110).
- [docs/failure_testing.md](docs/failure_testing.md): failure/recovery scenario matrix and
  results (§107).
- [docs/powerbi.md](docs/powerbi.md): connecting Power BI, the model, measures and dashboards.
- [MASTER_BUILD_PROMPT.md](MASTER_BUILD_PROMPT.md): the authoritative architecture contract.
- Tracking: [roadmap.md](roadmap.md), [current_state.md](current_state.md),
  [bugs_and_fixes.md](bugs_and_fixes.md).

## Repository layout

| Path | What |
|---|---|
| `app/` | FastAPI backend (auth, catalog, cart, wishlist, checkout, orders, reviews, `POST /events`) |
| `web/` | React + Vite + TypeScript frontend |
| `db/` | SQLAlchemy models, Alembic migrations, seed data |
| `events/` | Avro contracts (18 event types), producer, transports (logging / Kafka + Avro) |
| `kafka/`, `debezium/` | Topic/schema/connector registration; local Docker Compose versions |
| `azure/vm-stack/` | Cloud VM stack: Kafka, Schema Registry, Debezium Connect; `airflow/` with the DAGs |
| `databricks/` | Pipeline sources (`bronze_`, `silver_`, `silver_cdc_`, `gold_pipeline.py`), `silver_rules.py`, SQL views, `provision.ps1` |
| `scripts/` | Bootstrap, `simulate_traffic.py` (labelled simulated shoppers through the real API), `failure_tests.py` |
| `tests/` | pytest: DB constraints, API, events, Silver validation rules |

## Local development

Requires Docker Desktop, Python 3.12+ and Node 20+.

```bash
cp .env.example .env                  # DATABASE_URL etc.; EVENT_TRANSPORT=logging needs no Kafka
pip install -r requirements.txt
scripts/bootstrap.sh                  # or scripts/bootstrap.ps1: Postgres, migrations, seed
pytest tests/ -q                      # 203 passed, 2 skipped
uvicorn app.main:app --reload         # http://localhost:8000/docs
cd web && cp .env.example .env && npm install && npm run dev   # http://localhost:5173
```

A local Kafka + Debezium stack is available (`kafka/docker-compose.yml`,
`debezium/docker-compose.yml`) if you want the event and CDC path without the cloud.

## Cloud

1. **Postgres (Supabase)**: `alembic -c db/alembic.ini upgrade head`,
   `python db/seed/run_seed.py`, `python -m debezium.setup_postgres` (Debezium role, table
   ownership, `REPLICA IDENTITY FULL`).
2. **VM**: `azure/vm-stack/docker-compose.yml` (Kafka, Schema Registry, Connect), then
   `kafka/create_topics.py`, `kafka/register_schemas.py`, `debezium/register_connector.py`.
   Airflow: `azure/vm-stack/airflow/`, with a Databricks token in the VM-only `airflow.env`.
3. **Databricks**: `databricks/provision.ps1` (storage, workspace, Unity Catalog, NSG
   service-tag rule, pipeline, Silver/ops views).
4. **App → cloud Kafka**: run the API with
   `EVENT_TRANSPORT=kafka KAFKA_BOOTSTRAP_SERVERS=<vm>:29092 SCHEMA_REGISTRY_URL=http://<vm>:8081`.

**Cost**: the pipeline runs *triggered* (each update catches up, then stops) to protect the
credit budget. Set `continuous: true` for live real-time operation (~13s event → Silver). See
[docs/architecture.md §18](docs/architecture.md#18-cost).

Secrets never go into git: `.env` and `azure/vm-stack/airflow/airflow.env` are gitignored.
