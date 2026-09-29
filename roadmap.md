# Roadmap

Static plan-of-record. Phase order and semantics are locked by `MASTER_BUILD_PROMPT.md` §105;
Phase 0 is added for repo/tooling setup. Update the **Status** column when a phase changes
state — this file is not rewritten on every commit. Details of what's actually built live in
`current_state.md`.

| # | Phase | Scope | Status | Cloud dependency |
|---|---|---|---|---|
| 0 | Repo scaffold + tracking | Directory layout, git, `.gitignore`, `.env.example`, README, roadmap/current_state/bugs_and_fixes | Done | none |
| 1 | PostgreSQL schema | SQLAlchemy models, Alembic migrations, local Postgres via Docker, seed catalog data, constraint tests | Done | none (local Docker) |
| 2a | E-commerce backend API | FastAPI backend: auth, catalog, cart, wishlist, checkout, orders (atomic transaction + promotion engine) | Done | none (local Docker) |
| 2b | E-commerce frontend | React/Vite/TS SPA against the Phase 2a API | Done | none (local Docker) |
| 3a | Behavioral event contracts + server-side wiring | All 18 Avro event schemas, producer library + swappable transport (local `LoggingTransport` for now), 10 server-emitted event types wired into existing endpoints | Done | none |
| 3b | Client-emitted events | `POST /events` ingestion endpoint (optional auth), `X-Session-Id` header convention, frontend instrumentation for 7 of the 8 client-emitted event types | Done | none |
| 2c | Catalog & commerce enhancements | Currency fix (INR), product images/descriptions, reviews subsystem (seeded sample reviews), rating sort/filter, Buy Now (cart-bypassing checkout) | Done | none (local Docker) |
| 4 | Kafka + Schema Registry | KRaft single-broker matching final topology (10 topics, 38 partitions), self-hosted Schema Registry, `KafkaAvroTransport` — now deployed on the Azure VM (`azure/vm-stack/`), local Docker version also still available | Done | Azure VM (`ekadai-vm`, East US) |
| 5 | Debezium + PostgreSQL CDC | Debezium Connect, dedicated Postgres role + filtered publication + replication slot, single connector covering 5 CDC tables — now running on the Azure VM against Supabase's direct connection | Done | Azure VM + Supabase |
| — | Cloud migration (Postgres → Supabase, Kafka+Debezium → Azure VM) | Full chain verified end-to-end: app → Supabase (pooler) → Debezium (Azure VM, IPv6) → Kafka (Azure VM) → consumed from local machine | Done | Azure VM + Supabase |
| 6 | Bronze ingestion | `bronze_events` + 5 `bronze_cdc_*` tables on Delta (Unity Catalog `ekadai_databricks.bronze`), continuous real-time streaming from the VM's Kafka via a serverless Lakeflow Declarative Pipeline | Done | Azure Databricks (Premium, serverless) + ADLS Gen2 |
| 7 | Silver events + validation | `silver_events`, `silver_event_filters`, `silver_event_quarantine`, dedup, validation — streaming in the same continuous pipeline as Bronze (~13s event → Silver) | Done | Databricks |
| 8 | Silver CDC + SCD2 | `silver_cdc_orders/order_items` (change log), `silver_products/categories/users` (SCD2) — streaming in the same pipeline, ordered by WAL position (~23s DB commit → Silver); 5 CDC tables set to `REPLICA IDENTITY FULL` | Done | Databricks |
| 9 | Reference resolution | `reference_resolution_queue`, streaming resolution, in-place Silver correction — race-free single-flow design, ~8s from reference arrival to corrected event | Done | Databricks |
| 10 | Late-data replay | `is_late`/`is_too_late` (10 + 5 min, configurable), `late_data_replay_queue`, hourly Airflow `late_data_replay` DAG (Airflow now on the VM) | Done | Databricks + Airflow (Azure VM) |
| 11 | Gold facts/dimensions | `dim_*`, `fact_events/sessions/orders/order_items` as materialized views (`databricks/gold_pipeline.py`) | Built — verify at restart | Databricks |
| 12 | Gold aggregates | `agg_user_activity/conversion_funnel/product_performance/daily_revenue/order_metrics` + `agg_product_attribution` | Built — verify at restart | Databricks |
| 13 | Observability | `ops` schema: event log, `pipeline_runs`, stage metrics, latency, data quality, queues, Kafka lag, retention; DAGs `kafka_cdc_health`, `backfill_reconcile`, `lakehouse_maintenance` | Built — verify at restart | Databricks + Airflow |
| 14 | Power BI | Guide: connection, model, measures, pages (`docs/powerbi.md`); report built by the user in Power BI Desktop | Guide done — report pending | Power BI Desktop |
| 15 | Failure/recovery testing | `scripts/failure_tests.py` + matrix `docs/failure_testing.md`; many scenarios already verified in Phases 7–10 | Partly verified — rest at restart | — |
| 16 | Documentation + portfolio polish | `README.md`, `docs/architecture.md` (§110 items, diagram) | Done | — |

## Notes

- Phases 4/5's Azure deferral (avoid early spend) was lifted once the user chose to use their
  Azure free credits for real Databricks (Phase 6) — since Databricks can't reach a Kafka
  broker running on a local machine, Kafka/Debezium/Postgres all moved to the cloud together
  (Postgres → Supabase, Kafka+Debezium → an Azure VM) rather than deferring further. See
  `current_state.md` for the full migration detail.
- The Databricks workspace now exists (Phase 6). Phases 7–13 build on it; the user chose
  real-time analytics as the end goal, so downstream layers should stay streaming, not batch.
- No phase is marked Done without its verification steps actually having been run.
