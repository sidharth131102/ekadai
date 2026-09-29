# Ekadai: project deep dive

A complete explanation of what was built, which services it uses and why, how data moves, the
data models, the business rules, the key queries, the optimisations, how correctness is
guaranteed, and what was verified. It's written so you can answer detailed questions about any
part of the system. Section references like §54 point to the architecture contract in
[`MASTER_BUILD_PROMPT.md`](../MASTER_BUILD_PROMPT.md).

---

## 1. The project in one paragraph

Ekadai is a working e-commerce store (FastAPI + React on PostgreSQL) with a **real-time data
platform** behind it.
- Every user action emits a contract-validated **Avro event** to **Kafka**. Every change to the
  store's authoritative tables is captured from the Postgres write-ahead log by **Debezium
  (CDC)**.
- Both streams land in an **Azure Databricks lakehouse**, built as one serverless Lakeflow
  Declarative Pipeline:
  - **Bronze** keeps raw data;
  - **Silver** validates, deduplicates, quarantines, keeps SCD2 history, resolves late-arriving
    references and flags late data;
  - **Gold** is a star schema of dimensions, facts and aggregates.
- **Airflow** handles late-data replay, backfill with reconciliation, health sampling and
  maintenance.
- **Power BI** sits on Gold for business analytics and on an `ops` schema for platform
  observability.
- End to end: a click on the live site reaches Silver in about **13 s** and the Gold dashboards
  in about **1.5 min** in continuous mode.

**Live pieces** (while the cloud is switched on):
- storefront: https://ekadai-rouge.vercel.app
- API: https://ekadai-api.eastus.cloudapp.azure.com
- code: https://github.com/sidharth131102/ekadai

---

## 2. What was built (inventory)

| Layer | What exists | Where |
|---|---|---|
| Storefront | React + Vite + TypeScript SPA: 11 pages (home, listing with search/filter/sort, product detail with reviews, cart drawer, checkout, buy-now, orders, order detail, wishlist, profile, auth), client event tracking | `web/` |
| API | FastAPI: auth (JWT), catalog, cart, wishlist, checkout snapshots, orders + cancellation, reviews, `POST /events` | `app/` |
| OLTP database | 13 tables, Alembic migrations, seed (7 categories, 43 products, 129 reviews), DB-level constraints | `db/` |
| Event contracts | 18 Avro schemas, envelope builder, validating producer, swappable transports (logging / Kafka + Avro) | `events/` |
| Streaming backbone | Kafka (KRaft, 10 topics, 38 partitions), Schema Registry, Debezium Connect | `azure/vm-stack/`, `kafka/`, `debezium/` |
| Lakehouse | One Lakeflow pipeline with 4 sources: Bronze, Silver events, Silver CDC, Gold | `databricks/*_pipeline.py` |
| Validation rules | Pure-Python rule engine, 59 unit tests | `databricks/silver_rules.py` |
| SQL views | Spec-shaped SCD2 views; observability views | `databricks/silver_views.sql`, `databricks/ops_views.sql` |
| Orchestration | Airflow DAGs `late_data_replay`, `kafka_cdc_health`, `backfill_reconcile`, `lakehouse_maintenance` | `azure/vm-stack/airflow/dags/` |
| BI | Power BI project (PBIP: TMDL model + PBIR report), 25 tables, 23 relationships, 33 measures, 9 pages; generated from live schemas | `powerbi/` |
| Deployment | Vercel (frontend), Caddy + Let's Encrypt in front of the API on the VM, Databricks provisioning script | `web/vercel.json`, `azure/vm-stack/api/`, `databricks/provision.ps1` |
| Tooling | Traffic simulator (real API, labelled `sim-`), failure-scenario injector | `scripts/` |
| Docs | Architecture, failure-testing matrix, Power BI guide, this file, tracking docs | `docs/`, `*.md` |

---

## 3. Services: what, how, and why

| Service | Used for | How it's configured | Why this choice (and what was rejected) |
|---|---|---|---|
| **PostgreSQL on Supabase** | Authoritative application state | App → **session pooler** (IPv4); Debezium → **direct connection** (IPv6), because logical replication can't pass through a pooler | Managed and free. Postgres was required (§111: not MongoDB). Self-hosting on the VM was the fallback if IPv6 didn't work; it did. |
| **FastAPI + SQLAlchemy + Alembic** | API and migrations | JWT auth; order creation in one DB transaction; events emitted after the response via `BackgroundTasks` | Async-friendly, typed (Pydantic), fast to build; Alembic gives reproducible schema history |
| **React + Vite (TypeScript)** | Storefront | `X-Session-Id` per browser tab, fire-and-forget event tracking | Standard SPA stack; static build deploys anywhere |
| **Vercel** | Hosting the storefront | Static build, SPA rewrite in `web/vercel.json`, `VITE_API_BASE_URL` set at build time | Free, global CDN, one-command deploys |
| **Azure VM** (Standard_D2ns_v6, East US) | Kafka, Schema Registry, Debezium, Airflow, API, Caddy (all Docker) | Dual-stack networking (IPv6 needed for Supabase's direct connection); NSG rules restrict Kafka/SSH/Airflow to the developer IP and allow Databricks serverless via the `AzureDatabricksServerless.EastUS` service tag | Legacy VM sizes (B2ms, D2s_v3) had non-adjustable zero quota on the new subscription; a current-generation size deployed first time. One VM keeps cost tiny. |
| **Apache Kafka (KRaft)** | Durable, ordered event and CDC transport | Single broker, no ZooKeeper (§37), 7-day retention, per-entity partition keys | The spec's backbone (§111 rules out Pub/Sub, Event Hubs, Confluent Cloud). KRaft removes ZooKeeper. |
| **Confluent Schema Registry** | Schema governance | BACKWARD compatibility; **TopicRecordNameStrategy** so one topic can carry several record types | Contracts enforced at the producer; the consumer resolves any schema by the id in each message |
| **Debezium (Kafka Connect)** | CDC from Postgres | `pgoutput`, filtered publication on 5 tables, dedicated slot, initial snapshot, RegexRouter to `cdc-*` topics, key override for `order_items` | Log-based CDC captures every committed change in order with transaction metadata, without app changes or polling |
| **Azure Databricks** (Premium, Unity Catalog) | Lakehouse compute and governance | **Serverless Lakeflow Declarative Pipeline**; UC catalog `ekadai_databricks` with schemas `bronze`/`silver`/`gold`/`ops` on **ADLS Gen2** via an access connector | Serverless jobs reject infinite triggers; classic clusters hit VM stockouts and quota limits; serverless *pipelines* support continuous streaming. Premium is the only SKU for new workspaces. |
| **Databricks SQL warehouse** (serverless, Small) | Ad-hoc SQL, Airflow SQL tasks, Power BI | Auto-stop at **1 minute** | Pay only while queried |
| **Apache Airflow** (standalone on the VM) | Replay, backfill/reconciliation, health sampling, maintenance | Joins the Kafka Docker network; talks to Databricks with a scoped token held only on the VM | The spec names Airflow for safety, recovery and maintenance (§61, §67), never for normal resolution |
| **Caddy + Let's Encrypt** | HTTPS for the public API | Azure DNS label `ekadai-api.eastus.cloudapp.azure.com`; automatic certificates | An HTTPS Vercel page can't call an HTTP API (mixed content); Caddy was the smallest reliable fix |
| **Power BI Desktop** | Business and platform dashboards | PBIP generated from live schemas; Import (screenshots) or DirectQuery + page refresh (live); Databricks personal access token | Required BI layer (§103). Generating the model as code keeps it reproducible. |

---

## 4. One order, end to end

```
Browser (Vercel) ──HTTPS──► Caddy ─► FastAPI ─┬─ SQL transaction ─► Postgres (Supabase)
                                             │                          │ WAL (pgoutput)
                                             │                          ▼
                                             │                   Debezium ─► cdc-orders / cdc-order-items
                                             └─ Avro event ─► Kafka (order-events, checkout-events …)
                                                                 │
                         Lakeflow pipeline (serverless) ◄────────┘
                         Bronze ─► Silver ─► Gold (materialized views) ─► Power BI
```

1. **Checkout**: `POST /checkout/start` prices the cart from the DB (promotion engine), returns
   a `checkout_id`, and emits `checkout_started` with gross, discount and net values.
2. **Place order**: `POST /orders` runs **one transaction**:
   - re-validate the lines and lock the cart;
   - insert `orders` (status `CONFIRMED`) and `order_items` (historical unit price, discount,
     line revenue);
   - snapshot the shipping address and clear the cart.

   After commit, `order_created` is emitted (a behavioral milestone only).
3. **CDC**: Debezium reads the committed WAL records and publishes `op=c` for the order and
   each item, with `txId`, `lsn` and `ts_ms`. `order_items` are keyed by `order_id`, so one
   order's lines stay on one partition, in order.
4. **Bronze** (a few seconds): decodes Confluent-framed Avro (schema id → Schema Registry) and
   keeps the full envelope, the raw bytes and Kafka lineage.
5. **Silver** (~13 s from the click for events, ~23 s from DB commit for CDC):
   - the event is validated, deduplicated by `event_id`, and checked for references;
   - the order change lands in `silver_cdc_orders`.
6. **Gold** (~1.5 min in continuous mode):
   - `fact_orders` / `fact_order_items` recompute with the new order (current status from CDC,
     historical prices);
   - the aggregates follow;
   - Power BI in DirectQuery with 10 s page refresh shows Orders +1.
7. **Cancel** later: `CONFIRMED → CANCELLED` is an UPDATE, so CDC carries
   `status_before = CONFIRMED` (REPLICA IDENTITY FULL). Gold keeps the sale on the order date
   and records the cancellation on the **cancellation date** (§90).

---

## 5. OLTP data model (PostgreSQL)

13 tables:
- `users`, `addresses`
- `categories`, `products`
- `cart`, `cart_items`, `wishlist`, `wishlist_items`
- `promotions`, `promotion_targets`
- `orders`, `order_items`
- `reviews`

UUID primary keys throughout.

| Rule | How it's enforced |
|---|---|
| Money is exact | `NUMERIC(18,2)` everywhere; Python `Decimal`; never float (§111) |
| Orders are born `CONFIRMED`; the only transition is → `CANCELLED` | `order_status` enum; no PENDING state (§111) |
| Order header is internally consistent | `CHECK total_amount >= 0`, `item_count > 0`, `total_quantity > 0`, `item_count <= total_quantity`, confirmation/cancellation timestamp consistency |
| Order line arithmetic | `CHECK quantity > 0`, `unit_price >= 0`, `discount_amount >= 0`, `discount_amount <= quantity × unit_price`, `line_revenue = quantity × unit_price − discount_amount`; `UNIQUE(order_id, product_id)` |
| Historical truth | `order_items.unit_price` / `discount_amount` / `line_revenue` and `orders.shipping_*` are snapshots at purchase, so analytics never use today's price or address (§85, §111) |
| One open cart per user; no duplicate lines | Partial unique index on the active cart; `UNIQUE(cart_id, product_id)`, `UNIQUE(wishlist_id, product_id)` |
| Reviews | `CHECK rating BETWEEN 1 AND 5`; partial `UNIQUE(product_id, user_id) WHERE user_id IS NOT NULL` |
| Status lifecycles | Enums `account_status`, `product_status`, `category_status`, `cart_status`, `discount_type`, `promotion_target_type` |
| Query performance | Indexes on `orders(user_id)`, `(status)`, `(created_at)`, `(cancelled_at)`; promotion lookup indexes |

Five tables are CDC-captured (§45): `users`, `products`, `categories`, `orders` and
`order_items`. Carts, wishlists, promotions, addresses and reviews are deliberately not
captured; their business meaning reaches the lakehouse through behavioral events.

---

## 6. Business rules

- **Promotion engine** (`app/services/promotions.py`):
  - Candidates target a PRODUCT, a CATEGORY or SITEWIDE. The **highest priority** eligible
    promotion wins; ties go to the earlier `created_at`, then `promotion_id`. **No stacking.**
  - PERCENTAGE: `discount = qty × unit_price × pct / 100`. FIXED_AMOUNT: `discount = amount × qty`.
  - The discount is rounded once (half-up to 0.01) and clamped to `[0, gross]`.
  - `line_revenue = gross − discount`.
- **Checkout is a priced snapshot**, not a stored record (no `checkouts` table, §9). Order
  creation re-prices from the DB, so a client can't tamper with prices.
- **Buy Now** bypasses the cart completely. A buy-now order never reads, locks or changes the
  user's existing cart (tested).
- **Order creation is idempotent per `checkout_id`**: replaying the same checkout returns the
  same order and doesn't re-emit `order_created`.
- **Cancellation**: only `CONFIRMED` orders can move to `CANCELLED`, setting `cancelled_at`.
  Nothing is physically deleted.
- **Currency**: a single app-level `INR` (§6); stored on each order and line.
- **Events never break requests**: server events use `emit()`, which never raises. Client
  events use `emit_strict()`, which 4xx's a malformed payload so it can't vanish silently.
- **Client events can't forge server facts**: `POST /events` only accepts the 8
  client-emittable types. `order_created` and the other server events are rejected.

---

## 7. Behavioral events

**Envelope** (identical for all 18 types):
- `event_id` (UUID)
- `event_type`, `schema_version`
- `event_timestamp` (epoch ms, user-action time)
- `producer`
- `context{user_id, session_id}`
- `device{device_type, operating_system, browser}` (parsed server-side from the User-Agent)
- `payload` (type-specific)

| Topic (partitions) | Event types → partition key |
|---|---|
| `user-events` (3) | user_registered, user_login, user_logout → `user_id` |
| `product-events` (6) | page_view, search, filter_applied, sort_applied, product_view → `session_id` |
| `cart-events` (4) | add_to_cart, remove_from_cart → `cart_id`; wishlist_added/removed → `user_id`; wishlist_view → `session_id`; buy_now_clicked → `checkout_id` |
| `checkout-events` (4) | checkout_started → `checkout_id` |
| `order-events` (3) | order_created, order_viewed, order_cancel_clicked → `order_id` |
| `cdc-users` (3), `cdc-products` (6), `cdc-categories` (3), `cdc-orders` (3), `cdc-order-items` (3) | Debezium; key = primary key, except order items → `order_id` |

- There are 10 topics and 38 partitions. Keys keep each entity's events in order on one
  partition.
- Money travels as the Avro `decimal` logical type.
- Subjects follow `TopicRecordNameStrategy`, e.g. `user-events-ekadai.events.user.UserRegistered`.

---

## 8. CDC details

- A dedicated `debezium` role owns the 5 tables. Postgres requires table ownership to add a
  table to a publication (discovered from real connector failures).
- `publication.autocreate.mode=filtered` gives exactly the 5 tables. The slot is
  `debezium_ekadai`, and `snapshot.mode=initial` loads existing rows first.
- **`REPLICA IDENTITY FULL`** makes UPDATE and DELETE carry the whole old row (§46). Without it,
  `status_before` is always null.
- Preserved all the way into Silver: operation, `txId` (transaction), `lsn` (change position),
  `source.ts_ms` (commit time) and the snapshot flag (§46–48).

---

## 9. Lakehouse data model

### Bronze (`ekadai_databricks.bronze`): raw, never loses anything

- **`bronze_events`**: `raw_payload` (decoded envelope as JSON), `event_id`, `event_type`,
  `schema_version`, `event_timestamp`, Kafka `topic/partition/offset/timestamp`,
  `ingestion_timestamp`, `raw_value` (original bytes) and `decode_error`.
- **`bronze_cdc_<entity>`** (×5): the Debezium envelope, `before_json` / `after_json`, `op`,
  `ts_ms`, `source_lsn`, `source_tx_id`, `source_snapshot`, and the same lineage.
- The decoder **never raises**. Garbage bytes become a row with `decode_error`, not a crashed
  stream (§42, §51).

### Silver (`ekadai_databricks.silver`): typed, validated, deduplicated, historical

| Table / view | Grain & key | Written by |
|---|---|---|
| `silver_events` (§54) | One row per `event_id`; ~40 typed columns (ids, timestamps, device, search, cart/checkout/order measures as `DECIMAL(18,2)`, lineage, `pipeline_version`, `validation_status`, `reference_status`, `reference_errors`, `is_late`, `is_too_late`) | AUTO CDC SCD1 keyed on `event_id` (upsert, so duplicates collapse) |
| `silver_event_filters` (§68) | One row per filter in a `filter_applied` event, key (`event_id`, `filter_index`) | AUTO CDC SCD1 |
| `silver_event_quarantine` (§64) | One row per invalid message, keyed by Kafka coordinates; `error_type`, `validation_error`; `raw_payload` or `base64:<bytes>` | AUTO CDC SCD1 |
| `silver_cdc_orders` (§69), `silver_cdc_order_items` (§70) | One row per change, key (id, `change_position`); `operation`, `change_timestamp`, `transaction_id`, `change_position`, `snapshot`, `status_before/after`, business columns | AUTO CDC SCD1 |
| `silver_products/categories/users_history` | SCD2, one row per version, `__START_AT` / `__END_AT` | AUTO CDC **SCD2** sequenced by `struct(lsn, commit_ts, snapshot)` |
| `silver_products`, `silver_categories`, `silver_users` (§71–73) | Spec-shaped views: `*_version_key`, `valid_from`, `valid_to`, `is_current` | UC views (`silver_views.sql`) |
| `reference_resolution_queue` (§62) | One row per (reference_type, reference_id) needed before it existed | Materialized view |
| `late_data_replay_queue` (§67) | One row per too-late event (ids only) | Airflow DAG (MERGE) |

#### Validation rules (`silver_rules.py`)

| Error type | Triggers |
|---|---|
| `MALFORMED` | Bronze couldn't decode it (bad magic byte, unknown schema id, truncated), or the payload isn't a JSON object |
| `SCHEMA_INVALID` | `event_id` not a UUID; unknown `event_type`; `schema_version < 1`; `event_timestamp` missing or ≤ 0; payload not an object; **event on the wrong topic**; **partition key missing** (e.g. `cart_id` for cart events) |
| `BUSINESS_RULE` | Quantities ≤ 0; negative money or counts; `cart_net_value ≠ gross − discount`; discount > gross; currency not `^[A-Z]{3}$`; blank search query; filters (§68): unknown type, price/rating needs a bound with min ≤ max, price ≥ 0, rating within 0–5, each filter type populates only its own field (brand → string, category → `category_id`, availability → boolean). One bad filter quarantines the whole event. |

- Invalid events are never dropped silently (§111). They go to quarantine with a readable
  reason, and Bronze still holds the original.
- `EVENT_ROUTING` in the rules must equal the app's registry, and a unit test fails if they
  drift apart.

#### SCD2 semantics (§47, §71–73, §92)

- **Ordering is by WAL position (LSN)**, never arrival order. An older change arriving late is
  inserted into history in the correct place instead of becoming "current".
- **Only real attribute changes create versions**:
  - products: name, category, brand, price, status;
  - categories: name, status;
  - users: city, state, account_status.

  `updated_at`, descriptions and so on update in place.
- **Duplicate CDC is dropped** before AUTO CDC by `dropDuplicatesWithinWatermark(key, lsn)`,
  with a 7-day watermark matching Kafka retention.
- **Deletes close the current version**; history is kept (§50).
- **Version keys** are `xxhash64(id, lsn)`: deterministic, so the same keys come back after any
  rebuild.
- **Snapshot-born versions** use `valid_from = created_at`. The snapshot only proves the row
  existed from then, and orders placed before the snapshot must still join to a version.
- **Users never carry** email, password or phone into Silver or Gold (§73).

#### Reference resolution (§60–63), and why it's race-free

- Each valid event's `user_id` (USER), `product_id` (PRODUCT) and `category_id` (CATEGORY) is
  checked **independently** against the ids CDC has delivered. An unknown product never implies
  an unknown category (§63).
- Status: RESOLVED (no references, or all known), UNRESOLVED (all unknown) or
  PARTIALLY_RESOLVED. The event stays `VALID`; unknown references are not a quarantine reason
  (§60).
- **The race**: a `user_registered` event reaches Silver in ~7 s, but the same user's CDC row
  takes ~14 s to reach Bronze. The event is routinely checked before its user exists.
- **The design**: `silver_events`' AUTO CDC source is a *union* of:
  - (a) new valid events;
  - (b) corrections: when a reference **first** appears in CDC (insert or snapshot), every
    event referencing it is **re-derived from Bronze** and re-emitted with recomputed status
    and a **higher sequence revision**. AUTO CDC then updates the same `event_id` row: no second
    row, no partial row.
- **Why it can't miss:** existence is looked up in the Bronze CDC tables, re-read every
  micro-batch, and those are the same tables the correction triggers stream from.
  - If the event reaches Bronze before the reference, the reference's arrival corrects it.
  - If it reaches Bronze after, its own arrival check already sees the reference.
- The first design read unresolved rows back from `silver_events`. The pipeline graph rejects
  a flow reading its own target (a cycle), which is why corrections re-derive from Bronze.

#### Late data (§65–67)

- `lateness = kafka_timestamp − event_timestamp`.
  - It uses Kafka's append time, not Bronze's ingestion time: a Bronze replay resets
    `ingestion_timestamp`, which would make history look late.
- `is_late` = lateness > watermark (10 min). `is_too_late` = lateness > watermark + allowed
  lateness (15 min). Both thresholds are pipeline config.
- Too-late events stay in Silver. **Gold admits them only after replay**: the Airflow DAG
  verifies the exact event in Bronze and marks its queue row `PROCESSED` (§66–67).
- Measured on real traffic: server-stamped events max 0.5 s; browser-stamped p99 5.6 s,
  max 6 s. 10 + 5 min is a generous starting point (§65 says to validate it empirically).

### Gold (`ekadai_databricks.gold`): the star schema

**Dimensions**

| Table | Key | Notes |
|---|---|---|
| `dim_date` (§80) | `date_key` = `YYYYMMDD` | 2026–2027 generated; ISO week, month/quarter names, weekend flag |
| `dim_user` (§77) | `user_key` = SCD2 version key | `registration_date`, `account_status`, `city`, `state`, validity; no PII |
| `dim_product` (§78) | `product_key` = version key | `category_key` = the category version valid when the product version began |
| `dim_category` (§79) | `category_key` = version key | SCD2 |
| `dim_device` (§81) | `device_key` = hash(type, OS, browser) | No device id, no SCD2 |

**Facts**

| Table | Grain | Key rules |
|---|---|---|
| `fact_events` (§82) | One behavioral event | "As-of" keys to user/product/category versions valid at event time; category from the event or implied by the product (§63); no Kafka lineage and no money (§82) |
| `fact_sessions` (§83) | One session | New session after **30 min inactivity** within a `session_id`; anonymous → login stays one session; `date_key` = start date; `converted` only if the order exists in the orders CDC (authoritative) |
| `fact_orders` (§84) | One order (not one per CDC change) | Current status = latest change by LSN; `date_key` = creation date; item counts from the current order items |
| `fact_order_items` (§85) | One order line | Historical price and discount; product version as of the order time |

**Aggregates**

| Table | Grain | Definitions |
|---|---|---|
| `agg_user_activity` (§86) | user × date | Action counts, `unique_products_viewed`, `total_cart_additions/removals` = quantity sums; anonymous activity not attributed |
| `agg_conversion_funnel` (§87) | date | Distinct sessions reaching view → cart → checkout → successful order; **abandoned** = checkout started, no successful order within **15 min**, and 15 min have passed; cancelled-order sessions; percentages are derived in BI, not stored |
| `agg_product_performance` (§88) | product × date | Views, unique viewers, cart adds, unique cart users, orders (distinct), units; **GMV = Σ qty × historical unit price**; **net = GMV − discount** |
| `agg_daily_revenue` (§90) | date × currency | Sales on the **order date**; cancellations on the **cancellation date**; `revenue_after_cancellations = net_transaction_sales − cancelled_order_value`; no tax, shipping or refunds |
| `agg_order_metrics` (§91) | order date × currency | Orders, confirmed, cancelled, total value, AOV, cancelled value, cancellation rate |
| `agg_product_attribution` (§89) | product | First view vs first purchase of the **same product**, purchase within **7 × 24 h** of the view, cross-session allowed; viewers, converters, rate, avg and median seconds |

**Why materialized views:** every Gold grain is a pure function of Silver. That gives three
properties for free:
- reference resolution, late replay and cancellations correct Gold automatically on the next
  refresh;
- reruns are idempotent;
- there's no bespoke correction logic.

**Admission rule** (§66): an event reaches Gold if it's `NOT is_too_late`, or its replay record
is `PROCESSED`. Synthetic test products (`brand = 'zz-test'`) are excluded.

---

## 10. Key queries (the patterns worth explaining)

**"As-of" dimension join.** The version valid at the fact's time, falling back to the earliest
version when the fact predates it (e.g. an event fired a moment before the row committed):

```sql
SELECT s.*, d.user_key
FROM events s
LEFT JOIN gold.dim_user d ON d.user_id = s.user_id
QUALIFY row_number() OVER (
  PARTITION BY s.event_id
  ORDER BY CASE WHEN d.valid_from <= s.event_timestamp
                 AND (d.valid_to IS NULL OR s.event_timestamp < d.valid_to) THEN 0 ELSE 1 END,
           d.valid_from) = 1
```

**Sessionization** (§83): gaps-and-islands, a running sum of "new session" flags:

```sql
SELECT *, xxhash64(session_id, sum(new_session) OVER (PARTITION BY session_id
         ORDER BY event_timestamp, event_id ROWS UNBOUNDED PRECEDING)) AS session_key
FROM (SELECT *, CASE WHEN lag(event_timestamp) OVER w IS NULL
                       OR event_timestamp > lag(event_timestamp) OVER w + INTERVAL 30 MINUTES
                     THEN 1 ELSE 0 END AS new_session
      FROM admitted_events WINDOW w AS (PARTITION BY session_id ORDER BY event_timestamp, event_id))
```

**Current order state from a change log** (§84):

```sql
SELECT * FROM silver.silver_cdc_orders WHERE operation <> 'DELETE'
QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY change_position DESC) = 1
```

**Cancellation on its own date** (§90): sales are grouped by
`date_key(order.created_at)`, cancellations by `date_key(order.cancelled_timestamp)`, and the
two are FULL OUTER JOINed on (date, currency).

**SCD2 view mapping** (`silver_views.sql`):

```sql
xxhash64(product_id, __START_AT.change_position) AS product_version_key,
CASE WHEN __START_AT.snapshot THEN least(created_at, __START_AT.change_timestamp)
     ELSE __START_AT.change_timestamp END AS valid_from,
__END_AT.change_timestamp AS valid_to,
__END_AT IS NULL AS is_current
```

**Kafka lag** (`ops.kafka_lag`): latest broker offset (sampled by Airflow) minus the last
offset Bronze ingested, per partition, plus each partition's traffic share, which flags hot
partitions and imbalance.

---

## 11. Observability (`ekadai_databricks.ops`, §97–102)

- The pipeline **event log is published** as `ops.pipeline_event_log`.
- Views:
  - **`pipeline_runs`**: state, cause, duration, failures per update.
  - **`pipeline_stage_metrics`**: the Pipeline → Stage → Flow hierarchy (§99), with Bronze,
    Silver Events, Silver CDC, Reference Resolution and Gold; output rows, failed batches,
    backlog.
  - **`latency_metrics`**: hourly p50/p95 ingestion, processing and end-to-end latency (§58).
  - **`data_quality_metrics`**: decode failures, quarantine by type, quarantine rate, late and
    too-late, unresolved.
  - **`reference_resolution_status`**: backlog, oldest age, resolution latency, retries.
  - **`late_replay_status`**: backlog, success, failures, latency.
  - **`kafka_lag`** and **`cdc_connector_health`**.
  - **`retention_status`**: oldest record per table vs its §95 policy, with an overdue flag.
- Airflow writes `kafka_offsets`, `cdc_connector_status`, `backfill_audit` and
  `reconciliation_results`.

**Airflow DAGs**

| DAG | Schedule | What it does |
|---|---|---|
| `late_data_replay` | hourly | Queue too-late events (MERGE, stable `replay_id = xxhash64(event_id)`); verify the exact event in Bronze and Silver → `PROCESSED`, else `FAILED` with retries (max 3); prune processed rows after 30 days |
| `kafka_cdc_health` | 30 min | Sample all 38 partitions' offsets and the Debezium connector state |
| `backfill_reconcile` | manual, parameters | Rebuild selected Silver tables from Bronze (`full_refresh_selection`, recomputing Gold in the same update); 8 reconciliation checks; audit row with counts, verdict and `supersedes_backfill_id` |
| `lakehouse_maintenance` | daily | Prune ops samples; OPTIMIZE/VACUUM Airflow-owned tables; fail loudly on retention breaches |

---

## 12. Optimisations & cost decisions

| Decision | Effect |
|---|---|
| **One pipeline, four sources** | One compute instead of four; the pipeline orders dependencies; reference resolution relies on one flow's sequential micro-batches |
| **Serverless continuous only when needed**; triggered otherwise | Continuous bills 24/7. Triggered processes everything new, then stops, and Kafka's 7-day retention absorbs the gap. Switched on for demos. |
| **SQL warehouse auto-stop: 1 min** (from 10) | A short Airflow query no longer bills a 10-minute idle tail |
| **Replay DAG hourly, not every 15 min** | Avoids keeping the warehouse awake around the clock |
| **VM deallocated between sessions** | Standard-SKU public IPs are static, so Kafka's advertised address survives |
| **Native Spark parsing for CDC** (`from_json` + explicit casts), no Python UDF | Fast and vectorised; an unexpected encoding becomes a null, not a crash |
| **Validation UDF self-contained** (closure, `register_pickle_by_value`) | Runs on serverless workers without module-pickling failures |
| **Deterministic hashed keys** (`xxhash64`) | No sequence generators or joins to allocate keys; identical after rebuilds |
| **Gold as materialized views** | Self-correcting and idempotent; incremental refresh where possible |
| **Dedup before SCD2** (`dropDuplicatesWithinWatermark`, 7 days) | Bounded state; duplicates never create versions |
| **Correction triggers only on a reference's first appearance** | Product price updates don't re-emit old events |
| **Partition keys per entity** | Ordering where it matters (a cart, an order) with parallelism across entities |
| **DB-level constraints and snapshots** | Invalid money states are impossible, so no clean-up downstream |
| **Power BI: Import for screenshots, DirectQuery only for live demos** | The warehouse runs only while it's actually needed |

---

## 13. Correctness guarantees (and how each is achieved)

| Guarantee | Mechanism |
|---|---|
| No lost data | Kafka retention; Bronze keeps raw bytes and undecodable messages; quarantine instead of drop |
| No duplicate events | AUTO CDC keyed on `event_id` |
| No duplicate CDC rows or versions | Keys include the LSN; dedup before SCD2 |
| Correct history under reordering | SCD2 sequenced by LSN |
| Unknown references never cause loss or duplicates | Keep, flag, correct in place |
| Late data never silently dropped | Flagged; replay queue; gated Gold admission |
| Idempotent reruns | Stable ids, hashed keys, MERGE/upsert, deterministic transforms (§57) |
| Authoritative orders | Order facts come from CDC, never from the behavioral `order_created` (§111) |
| Historical revenue | Line-level snapshot prices; never today's price |
| Auditable recovery | `backfill_audit` + `reconciliation_results` |

---

## 14. How it was verified

- **Automated**: `pytest`, **203 passed, 2 skipped**.
  - API: auth, catalog, cart, wishlist, checkout, orders, cancellation, buy-now, reviews,
    events endpoint.
  - DB constraints.
  - Event schemas and producer.
  - 59 Silver validation rules, each run on real Avro round-trips.
- **Live, on the cloud stack** (details in `docs/failure_testing.md`):
  - malformed Avro → quarantined, pipeline kept running;
  - business-rule violation → quarantined;
  - duplicate event → one row;
  - filter rules;
  - duplicate CDC → no extra row;
  - out-of-order CDC → correct SCD2 order;
  - DELETE closes the version;
  - `status_before` on cancel;
  - an event before its reference → flipped to RESOLVED in ~8 s, same row;
  - §63 partial resolution;
  - 12- and 20-minute late events flagged correctly;
  - the replay DAG queued only the too-late one, was idempotent, and exercised the FAILED path.
- **Gold checks**: orders 9 = 9 = 9 across CDC, facts and aggregates; net sales = Σ line
  revenue to the paisa; every order line resolved to a product version; the only unresolved
  users are deliberate test ids.
- **Latency**:
  - event → Silver ~13 s (continuous);
  - DB commit → Silver SCD2 ~23 s;
  - reference correction ~8 s;
  - click → Gold ~1.5 min.

**Not yet exercised live**:
- the `backfill_reconcile` and `lakehouse_maintenance` DAGs (they load cleanly; they haven't
  been triggered);
- the broker-outage and Debezium-restart injections;
- the Gold late-replay admission scenario.

---

## 15. Notable problems solved (good interview stories)

- **Kafka topics vanished on restart.** The image's default log directory wasn't the mounted
  volume. Fixed with `KAFKA_LOG_DIRS` and verified by a restart.
- **Debezium needed table *ownership*.** `SELECT` isn't enough to add a table to a publication.
  On Supabase this also needed role membership and schema `CREATE` first.
- **IPv6 all the way down.** The VM host had IPv6 but the Docker containers didn't; the Compose
  network needed `enable_ipv6` with a distinct subnet.
- **Silent null timestamps.** fastavro turned `timestamp-millis` into a `datetime`, and JSON
  serialisation wrote it as a string that cast to null. Fixed by writing epoch ms.
- **Serverless UDF pickling.** An `lru_cache` helper pickled by reference and failed on
  workers. Rebuilt as a closure.
- **`status_before` always null.** Postgres's default replica identity. Fixed with `REPLICA
  IDENTITY FULL`.
- **Dependency cycle.** The first reference-resolution design read its own target. Redesigned
  to re-derive from Bronze, keeping it race-free.
- **Stale-dimension risk.** Gold read SCD2 through UC views, which hid the dependency from the
  pipeline graph. Gold now reads the pipeline's history tables directly.
- **Idle-connection 500s.** Supabase's pooler drops idle connections. Fixed with
  `pool_pre_ping` + `pool_recycle`.
- **Mixed content.** An HTTPS storefront can't call an HTTP API; fixed with Caddy and Let's
  Encrypt on an Azure DNS name.
- **Power BI DirectQuery vs auto date/time.** Auto date tables force Import mode. They were
  removed and auto date/time switched off.

---

## 16. Trade-offs and what I'd change at scale

- **Single Kafka broker, RF 1**: fine for a portfolio. Production needs ≥ 3 brokers, RF 3 and
  `min.insync.replicas = 2`.
- **Gold as materialized views**: exact and simple at this size. At scale the facts would
  become incremental streaming tables or MERGE-based upserts, keeping MVs for aggregates.
- **Retention on pipeline-managed tables is monitored, not enforced**: a DELETE under a
  streaming source breaks its readers. The fix is change-commit-skipping readers or
  in-pipeline expiry.
- **Airflow standalone (SQLite)**: fine for 4 low-frequency DAGs. Production would use
  Postgres metadata and a real executor.
- **Secrets in VM env files**: fine here. Production would use Azure Key Vault or Databricks
  secret scopes.
- **Triggered vs continuous**: the trade is latency against cost, and it's one setting.

---

## 17. Questions you're likely to be asked (short answers)

1. **Why both events and CDC?** CDC is the truth about state (orders, prices, users). Events
   describe behaviour that never touches the DB (views, searches, abandoned checkouts). Facts
   about orders come only from CDC.
2. **How do you avoid duplicates end to end?** Stable ids plus upsert semantics at every layer:
   `event_id`, (id, LSN) for CDC, dedup before SCD2, hashed Gold keys.
3. **What if an event references a product that doesn't exist yet?** It's kept as
   UNRESOLVED/PARTIALLY_RESOLVED and fixed in place when the product arrives (~8 s). There's a
   queue for visibility.
4. **What if CDC arrives out of order?** SCD2 sequences by LSN, so history is rebuilt in source
   order.
5. **How is late data handled?** Flagged by Kafka time − event time; too-late events are held
   out of Gold until the replay DAG verifies them.
6. **Why AUTO CDC for events, which aren't CDC?** It provides keyed upsert with sequencing,
   which gives dedup and in-place correction for free.
7. **How do you know Gold is right?** Reconciliation checks (facts = admitted Silver, one row
   per order/item, aggregates = facts); verified 9/9/9 and ₹ totals to the paisa.
8. **Why is revenue stored per line?** Historical price and discount are snapshotted at
   purchase; recomputing from today's price would be wrong (§111).
9. **How is cancellation reported?** The sale stays on the order date; the cancellation hits
   the cancellation date. History is never rewritten.
10. **What's the latency?** ~13 s to Silver, ~1.5 min to Gold in continuous mode.
11. **Why serverless Databricks?** Classic clusters hit VM quota and stockouts, and serverless
    pipelines support continuous streaming without cluster management.
12. **What does it cost and how did you control it?** Continuous serverless is the main cost.
    It runs triggered by default, the warehouse auto-stops at 1 min, DAGs run hourly, and the VM
    is deallocated between sessions.
13. **How would you backfill?** The `backfill_reconcile` DAG rebuilds from Bronze, reconciles
    and audits; corrective runs supersede earlier ones.
14. **What happens if Kafka goes down?** The app keeps serving; the producer buffers and
    retries; Bronze catches up from offsets. A Bronze outage under 7 days is recoverable from
    Kafka.
15. **How are schemas evolved?** BACKWARD compatibility in the Registry; Bronze resolves every
    message's schema id, so no pipeline change is needed.
16. **What's in Bronze vs Silver vs Gold?** Raw and lossless; typed, validated and historical;
    business-shaped star schema.
17. **Is PII protected?** Email, password and phone never leave the OLTP database or Bronze's
    raw CDC; Silver and Gold users carry only city, state, status and dates.
18. **Why a star schema?** Conformed dimensions for slicing; facts at clear grains; BI-friendly
    relationships (no fact-to-fact joins, §75).
19. **How is a session defined?** 30 minutes of inactivity within a browser session id. Login
    doesn't break it, and it can cross midnight (§83).
20. **What would you improve first?** A multi-broker Kafka, Key Vault for secrets, incremental
    fact tables, and enforced retention.

---

## 18. Numbers cheat-sheet

| | |
|---|---|
| Event types / topics / partitions | 18 / 10 / 38 |
| OLTP tables / CDC tables | 13 / 5 |
| Bronze / Silver / Gold objects | 6 / 10 (+3 SCD2 views) / 15 (5 dims, 4 facts, 6 aggregates incl. attribution) |
| Ops views + tables / Airflow DAGs | 9 + 4 / 4 |
| Tests | 203 passed, 2 skipped (59 Silver rules) |
| Latency | ~13 s click → Silver; ~23 s commit → SCD2; ~8 s reference correction; ~1.5 min → Gold |
| Late thresholds | watermark 10 min, allowed lateness 5 min (observed max 6 s) |
| Power BI | 25 tables, 23 relationships, 33 measures, 9 pages |
| Seed catalog | 7 categories, 43 products, 129 reviews |
