# Bugs and Fixes

Reverse-chronological log of real issues hit during development or the spec's
failure-injection testing (`MASTER_BUILD_PROMPT.md` §107). Entries are added as issues
actually occur — this is not a pre-filled checklist.

Template per entry:

```
## YYYY-MM-DD — short title

**Phase:** N — name
**Symptom:** what was observed
**Root cause:** why it happened
**Fix:** what changed
**Status:** Open / Fixed / Won't Fix (with reason)
```

---

## 2026-09-29 — Power BI DirectQuery refused to open: auto date tables force Import mode

**Phase:** 14 — Power BI
**Symptom:** After switching the user-customised report to DirectQuery: "DirectQuery partitions
are not allowed in 'dim_user' because it has a datetime-to-date relationship with another
table."
**Root cause:** While the report was in Import mode, Power BI Desktop's *Auto date/time* had
added 30 hidden `LocalDateTable_*` / `DateTableTemplate_*` tables, linked to every datetime
column through `variation` blocks and relationships. Those relationships need Import mode.
**Fix:** Deleted the auto date tables, their 29 `variation` blocks and 29 relationships (52 → 23,
the model's own), and their model refs. Set `__PBI_TimeIntelligenceEnabled = 0`. The user's
report and visuals were untouched (no visual used the hierarchies; checked first). Opened in
DirectQuery with live data.
**Status:** Fixed. `docs/powerbi.md` records this gotcha, along with "don't regenerate over a
customised report", which cost one round of the user's edits before they were recovered
from the still-open Desktop session.

## 2026-09-29 — Gold dimensions could be built from stale SCD2 data (dependency hidden by UC views)

**Phase:** 11 — Gold
**Symptom:** The first successful update logged warnings: "The downstream table
'…silver_users_history' is referenced when creating the upstream … 'gold.dim_user'. Circular
dependencies are not supported". The same appeared for categories.
**Root cause:** Gold read SCD2 data through the Unity Catalog views `silver_users` /
`silver_categories` (created outside the pipeline). The pipeline can't see through a UC view,
so it didn't know `dim_user` depends on `silver_users_history` and couldn't order the refresh.
The dimensions could have been computed before the history tables updated.
**Fix:** `gold_pipeline.py` reads the pipeline's `*_history` tables directly, with the same
mapping as the views (`scd2()` helper). The next update completed with 0 warnings. The UC views
remain for humans and BI.
**Status:** Fixed.

## 2026-09-29 — Gold session facts failed analysis: ambiguous `user_id`

**Phase:** 11 — Gold
**Symptom:** `[AMBIGUOUS_REFERENCE] Reference 'user_id' is ambiguous, could be: e.user_id,
o.user_id` in `fact_sessions` and `agg_conversion_funnel`.
**Root cause:** The per-session aggregation joined events to current orders, and both have
`user_id`. The first draft left columns unqualified. It was only syntax-checked offline, and
the first live run caught it.
**Fix:** Fully qualified every column in `SESSION_FACTS`.
**Status:** Fixed.

## 2026-09-29 — Airflow DAG would have kept the SQL warehouse running most of the time

**Phase:** 10 — Late-data replay (caught right after deploying)
**Symptom:** None billed yet; found by reviewing the schedule against the warehouse settings.
The replay DAG ran every 15 min, and the serverless SQL warehouse auto-stops only after 10 idle
minutes. Each run's few seconds of SQL would have kept the warehouse up for ~11 of every 15
minutes, all day, on top of the always-on pipeline and against a fixed credit budget.
**Root cause:** Default warehouse auto-stop (10 min) paired with a short DAG interval.
**Fix:** Warehouse `auto_stop_mins` set to 1 (the minimum). The DAG schedule is now hourly; the
spec only requires too-late data to be replayed "later" (§66). Both are recorded in
`databricks/provision.ps1`. Exact spend isn't visible from here: the Azure usage API returns no
cost for this credit subscription, and Databricks `system.billing` tables aren't enabled.
**Status:** Fixed.

## 2026-09-29 — Pipeline rejected the first reference-resolution design as a dependency cycle

**Phase:** 9 — Reference resolution
**Symptom:** The update failed at graph analysis: `Graph is not topologically sorted. There is a
cycle between ekadai_databricks.silver.silver_events and silver_events_valid.`
**Root cause:** The correction side read still-unresolved rows back from `silver_events`, the
same table its flow writes to. `spark.read.table(<fully-qualified name>)` doesn't get around
this: the pipeline resolves any read of one of its own datasets as a graph dependency, so a
flow reading its own target is a cycle.
**Fix:** Corrections now re-derive the affected events from `bronze_events` (read statically,
through the same projection and validation as new events) instead of reading `silver_events`.
It's still race-free: an event already in Bronze when its reference lands is corrected, and one
arriving later is checked on its own arrival. Only a reference's first appearance (insert or
snapshot) triggers corrections. The platform's automatic retry of the refresh picked up the
fixed code and completed with 0 warnings.
**Status:** Fixed.

## 2026-09-29 — First API request after idling returned 500: Supabase pooler dropped the pooled connection

**Phase:** 2a — backend (found during Phase 8 verification)
**Symptom:** `POST /auth/register` returned 500 after the dev server had been idle for hours.
Log: `psycopg.OperationalError: consuming input failed: server closed the connection unexpectedly`.
**Root cause:** `app/db.py` built its engine with no liveness check. Supabase's pooler closes
idle connections server-side, but SQLAlchemy's pool still handed that dead connection to the
next request. Local Docker Postgres never idles connections out, so this never showed up before
the cloud migration.
**Fix:** `create_engine(..., pool_pre_ping=True, pool_recycle=300)`. A cheap ping on checkout
swaps out dead connections, and connections are retired before the pooler's idle cutoff. After
restarting the server, the same request succeeded, followed by the whole register → order →
cancel flow.
**Status:** Fixed.

## 2026-09-29 — CDC UPDATEs arrive with `before = null` (Postgres default replica identity)

**Phase:** 8 — Silver CDC + SCD2 (found during planning)
**Symptom:** Would have left `silver_cdc_orders.status_before` always null. Confirmed live: the
test cancel shows `status_before = NULL`, `status_after = CANCELLED`.
**Root cause:** All five CDC tables use `REPLICA IDENTITY DEFAULT`, so Postgres only writes the
primary key of the old row to WAL. Debezium therefore emits `before = null` for UPDATEs and a
PK-only `before` for DELETEs. §46 requires the full old row.
**Fix:** `debezium/setup_postgres.py` now runs `ALTER TABLE ... REPLICA IDENTITY FULL` for the 5
tables (idempotent, metadata only, applies to new changes). The user applied it to Supabase
(`python -m debezium.setup_postgres`), since it was blocked for me as a shared-database change.
Verified: `relreplident = 'f'` on all 5 tables, and a new order placed and cancelled through the
app now shows `status_before = CONFIRMED`, `status_after = CANCELLED` in `silver_cdc_orders`.
Changes from before the fix keep their null `before` (it can't be back-filled).
**Status:** Fixed.

## 2026-09-27 — A pipeline settings change restarted without the full refresh it needed

**Phase:** 7 — Silver events + validation
**Symptom:** After adding the Silver source and the two new Bronze columns, the pipeline
restarted by itself, but its update showed `full_refresh: false`. The Bronze column change
needed a full refresh to take effect.
**Root cause:** Saving new pipeline settings automatically restarts a continuous pipeline with
a normal (incremental) update. The separate `start-update --full-refresh` request that should
have followed was lost when the network dropped.
**Fix:** Re-issued `databricks pipelines start-update <id> --full-refresh` and checked that the
new update reported `full_refresh: true` before verifying any data. `databricks/provision.ps1`
now notes that a settings change alone never full-refreshes.
**Status:** Fixed.

## 2026-09-27 — Every `bronze_events.event_timestamp` was null

**Phase:** 6 — Bronze ingestion (found during Phase 7)
**Symptom:** `event_timestamp` was null on all 17 rows of `bronze_events`, even though every
`raw_payload` clearly contained a timestamp. Found while building Silver, which needs it.
**Root cause:** fastavro decodes Avro `timestamp-millis` into a Python `datetime`. The decoder's
`json.dumps(..., default=str)` wrote that as a date string (`"2026-09-26 17:47:22.728000+00:00"`),
and the column's `cast("long")` quietly turns a string like that into null. Nothing errored.
**Fix:** The decoder's JSON fallback now writes a `datetime` as epoch milliseconds, the value
actually on the wire. Other logical types (Decimal, UUID) are still written as strings. Full
refresh re-read everything from Kafka. Verified afterwards: 0 null `event_timestamp` in Bronze
or Silver. The Silver-rule tests serialize envelopes the same way, so they would catch a regression.
**Status:** Fixed.

## 2026-09-27 — Pipeline UDF failed on every worker: lru_cache helper doesn't pickle

**Phase:** 6 — Bronze ingestion
**Symptom:** All six pipeline flows started, then failed ~40s later and retried in a loop;
tables were created but stayed empty. Worker exception:
`AttributeError: Can't get attribute '_schema_for_id' on <module 'pyspark.databricks.workerwrap'>`.
**Root cause:** The Avro-decode UDF called a module-level helper wrapped in `functools.lru_cache`.
Spark pickles UDFs to ship them to workers; cloudpickle serializes plain functions by value, but
`lru_cache` wrappers pickle *by reference* (module + name), and that module doesn't exist on the
worker. The original standalone job scripts had the same latent bug — they never got far enough
to run it because of the compute problems below.
**Fix:** The decoder is now built by a factory that returns a closure with its own plain-dict
schema cache and all imports inside the function — everything pickles by value. Verified: no
flow failures after redeploying, and all six tables filled with the expected rows.
**Status:** Fixed.

## 2026-09-27 — Databricks serverless jobs reject continuous streaming triggers

**Phase:** 6 — Bronze ingestion
**Symptom:** After switching the jobs to serverless compute to escape VM-capacity problems, the
run failed with `[INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED] Trigger type ProcessingTime is not
supported for this cluster type. Use a different trigger type e.g. AvailableNow, Once.`
**Root cause:** A platform limitation, not a configuration error — serverless *job* compute only
runs bounded streaming triggers. Real-time (continuous) streaming isn't possible there.
**Fix:** Moved Bronze ingestion to a Lakeflow Declarative Pipeline in serverless *continuous*
mode, which does support indefinite streaming. Data model unchanged.
**Status:** Fixed (worked around by choosing a different Databricks product).

## 2026-09-27 — Classic Databricks clusters couldn't acquire VMs; Standard SKU also deprecated

**Phase:** 6 — Bronze ingestion
**Symptom:** Workspace creation with `--sku standard` failed (`DatabricksStandardSkuNotSupported`
— Premium is now the only option). Then job clusters failed repeatedly: `Standard_DS3_v2` hit
`CLOUD_PROVIDER_RESOURCE_STOCKOUT`, `Standard_D4ds_v5` hit `QuotaExceeded` (family quota 0),
`Standard_D2ns_v6` isn't a Databricks-supported node type, and `Standard_D4ds_v6` sat in
"Finding instances" for ~24 minutes.
**Root cause:** The same subscription-level capacity/quota limits that blocked the Kafka VM
yesterday apply to every VM Databricks tries to create in this subscription. Also, Databricks
only supports a curated subset of Azure VM sizes, so "the size that worked for the VM" isn't
automatically usable for clusters.
**Fix:** Used serverless compute, which runs in Databricks' own capacity pool and never creates
VMs in this subscription. Also learned: `databricks jobs reset` replaces *all* settings — a
partial reset silently wiped the job name and schedule once; use `jobs update` for partial
changes.
**Status:** Fixed (worked around).

## 2026-09-27 — Dev machine's public IP changed; app silently stopped publishing to Kafka

**Phase:** 6 — Bronze ingestion (found during latency verification)
**Symptom:** A test registration reached `bronze_cdc_users` (via Postgres → Debezium) but its
behavioral `user_registered` event never reached `bronze_events`. The dev-server log showed
continuous `Connect to ipv4#20.102.92.77:29092 failed` from the Kafka producer.
**Root cause:** The NSG allowed only yesterday's public IP (`111.92.124.14`); the machine's IP
had changed to `106.194.47.106` after a network reconnect. The producer buffers undeliverable
events for ~5 minutes, then drops them — so the failure is silent from the app's point of view,
as designed (`emit()` must never break a request).
**Fix:** Updated the `allow-kafka-broker` and `SSH` rules to the new IP; re-ran the test and the
event landed in Bronze in ~26s. Documented the one-line fix in `current_state.md` because it
will recur on a dynamic-IP connection.
**Status:** Fixed (recurring operational risk, documented).

## 2026-09-25 — Debezium publication creation needs table ownership, not just SELECT/REPLICATION

**Phase:** 5 — Debezium + PostgreSQL CDC
**Symptom:** The connector task failed twice in sequence while starting, each with a different
Postgres permission error: first `permission denied for database ekadai` (creating the
publication), then after granting `CREATE ON DATABASE`, `must be owner of table categories`.
**Root cause:** Postgres's `CREATE PUBLICATION ... FOR TABLE` (which
`publication.autocreate.mode=filtered` runs on Debezium's behalf) requires the invoking role to
either own each table or have `CREATE` on the database for the publication object itself —
`SELECT` and `REPLICATION` (what the `debezium` role had from the initial design) aren't
sufficient for either half. Two real permission requirements, not one, and not discoverable
from the design/planning stage — only from the connector's actual startup errors.
**Fix:** `debezium/setup_postgres.py` now also runs `GRANT CREATE ON DATABASE ekadai TO
debezium` and `ALTER TABLE <table> OWNER TO debezium` for exactly the 5 CDC tables. Flagged to
the user before running the ownership change specifically (a real, if low-risk, modification to
live application table metadata) — confirmed safe and approved, since `ekadai` is a Postgres
superuser and superusers bypass ownership/privilege checks entirely, so the app's own read/write
access to those tables is unaffected. Verified via `pg_tables.tableowner`, a live app health
check, and a full `pytest tests/ -q` run (144 passed, 2 skipped, unchanged) immediately after
the ownership transfer.
**Status:** Fixed.

## 2026-09-26 — Debezium Connect container had no IPv6 despite the VM host having real IPv6

**Phase:** Cloud migration — Kafka + Debezium deployed to the Azure VM
**Symptom:** After confirming the Azure VM itself has working IPv6 (direct `psql` to Supabase
succeeded over SSH on the host), registering the Debezium connector still failed at
preflight validation: `"Error while validating connector config: The connection attempt
failed."` — no useful detail beyond that.
**Root cause:** Docker containers don't automatically inherit the host's IPv6 connectivity.
`ip -6 addr show` inside the `ekadai-debezium-connect` container showed only loopback (`::1`) —
no real interface at all. Enabling IPv6 in `/etc/docker/daemon.json` (`"ipv6": true,
"fixed-cidr-v6": ...`) affects only Docker's *default* bridge network — a Compose project's own
custom network (what `docker compose up` actually creates and attaches containers to) needs
`enable_ipv6: true` declared explicitly in its own network config, and doesn't inherit the
daemon-level setting. A first attempt at fixing this also hit a second, smaller issue: reusing
the *same* `/64` subnet for both the daemon's default-bridge `fixed-cidr-v6` and the Compose
network's `ipam.config` subnet failed with "Pool overlaps with other one on this address space"
— they need distinct ranges.
**Fix:** `azure/vm-stack/docker-compose.yml` now declares its own `networks.default` block with
`enable_ipv6: true` and a `fd00:1234:5679::/64` subnet (distinct from the daemon's
`fd00:1234:5678::/64`). Verified via `docker exec ... ip -6 addr show` (container now gets a
real ULA address) and `curl -6` to a real IPv6-only endpoint from inside the container
(`200 OK`) — Docker's `ip6tables: true` handles NAT66 from the container's ULA to the host's
real IPv6 address automatically, the same way IPv4 NAT already works.
**Status:** Fixed.

## 2026-09-26 — Azure VM creation failed for legacy-generation VM sizes; CLI error was misleading

**Phase:** Cloud migration (Postgres/Kafka/Debezium → Azure)
**Symptom:** `az vm create` failed identically for `Standard_B2ms` (the size named in §37) across
three regions (Central India, Southeast Asia, East US), and for `Standard_D2s_v3` (a very common
alternative) in two of those regions — always `SkuNotAvailable: ... Capacity Restrictions`, even
with a completely vanilla, zero-custom-networking VM. Looked like broad datacenter capacity
shortage, which was implausible for such common sizes in East US specifically.
**Root cause:** The CLI's error message was generic/misleading. The real cause, only visible
through the Azure Portal's VM-creation wizard: this subscription's quota for **legacy VM
generations** (`Bsv1`, `Dsv3`, and similar older families) is permanently non-adjustable —
"Additional quota isn't available for this family" — confirmed via Portal -> Quotas ->
`Standard DSv3 Family`, shown as "Legacy - migration recommended, Adjustable: No". New Azure
subscriptions can't get more quota for these families at all, self-service or otherwise; only
**current-generation** families (e.g. `Dsv6`) are adjustable and actually deployable.
**Fix:** Used `Standard_D2ns_v6` (2 vCPU, 8 GiB — same profile as the originally-planned B2ms)
instead — deployed successfully on the first try. No further code/script changes needed; this
is purely a "pick a current-generation SKU name" fact for future re-provisioning.
**Status:** Fixed (worked around by SKU choice; not something to "fix" in our scripts beyond
noting it).

## 2026-09-26 — `debezium/setup_postgres.py` had a hardcoded DB name and didn't work against managed Postgres

**Phase:** Cloud migration — Postgres → Supabase
**Symptom:** Running the script against Supabase failed twice in sequence: first
`InsufficientPrivilege: must be able to SET ROLE "debezium"` on `ALTER TABLE ... OWNER TO`, then
(after fixing that) `InsufficientPrivilege: permission denied for schema public` on the same
statement. Separately, the script's `GRANT CREATE ON DATABASE ekadai` was hardcoded to the local
Postgres database name — silently wrong against Supabase, whose database is named `postgres`.
**Root cause:** The script was written and only ever tested against self-hosted local Postgres,
where the connecting role (`ekadai`) is a true superuser and bypasses every ownership/privilege
check. Supabase's `postgres` role is a privileged admin role but **not** a true superuser
(standard for managed Postgres): (1) transferring table ownership to a role requires the
connecting role to be able to `SET ROLE` to it first — true superusers get this implicitly, a
non-superuser admin role does not; (2) modern Postgres additionally requires the *new owner* to
hold `CREATE` (not just `USAGE`) on the containing schema before an ownership transfer succeeds.
**Fix:** Script now queries `CURRENT_USER`/`CURRENT_DATABASE()` at runtime instead of hardcoding
either, runs `GRANT debezium TO CURRENT_USER` before any ownership transfer (a harmless no-op
when the connecting role is already a true superuser), and grants `CREATE` alongside `USAGE` on
the schema. Now portable across self-hosted and managed Postgres without any config flag.
Verified via `pg_tables.tableowner` on Supabase and a clean idempotent re-run.
**Status:** Fixed.

## 2026-09-26 — Alembic silently broke on a percent-encoded password in DATABASE_URL

**Phase:** Cloud migration — Postgres → Supabase
**Symptom:** `alembic upgrade head` against Supabase failed immediately:
`ValueError: invalid interpolation syntax in '...<password with %40>...' at position 55`
(password redacted).
**Root cause:** `db/alembic/env.py` sets `sqlalchemy.url` via `config.set_main_option(...)`,
which writes through Python's `ConfigParser` — and `ConfigParser` treats a bare `%` as the start
of an interpolation reference (`%(name)s`) by default. The Supabase password needed URL
percent-encoding (`@` -> `%40`) since it contains an `@`, and that literal `%` broke parsing
before the URL ever reached SQLAlchemy.
**Fix:** `env.py` now escapes `%` to `%%` on the value passed to `set_main_option`, which
`ConfigParser` un-escapes back to a literal `%` when the value is read — the actual DB driver
still sees the correctly percent-encoded URL.
**Status:** Fixed.

## 2026-09-25 — Kafka's "persistent" volume mount was silently unused; a routine restart wiped all 10 topics

**Phase:** 5 — Debezium + PostgreSQL CDC (discovered while adding a listener to `kafka/docker-compose.yml` for Debezium to reach the broker, which required recreating the container)
**Symptom:** Recreating the `ekadai-kafka` container (a normal `docker compose up -d` after an
environment-variable change, not a volume/data operation) came back up completely empty — all
10 application topics and every registered Avro schema subject gone, despite
`kafka/docker-compose.yml` mounting a named volume (`kafka-data:/var/lib/kafka/data`)
specifically so this container is safe to recreate.
**Root cause:** The `apache/kafka:3.8.0` image's actual default `log.dirs` is `/tmp/kafka-logs`,
not `/var/lib/kafka/data` — confirmed directly from the container's own startup logs
(`dir=/tmp/kafka-logs` on every `LogLoader` line). The volume was mounted at a path Kafka never
actually wrote to, so every byte of "persisted" data was living on the container's ephemeral
writable layer the whole time; Phase 4's verification never caught this because the container
was never recreated until this phase's listener change forced it. A second-order failure
followed from the same root cause: after the wipe, Schema Registry's already-running process
(not yet restarted itself) auto-triggered Kafka's `auto.create.topics.enable` fallback for the
now-missing `_schemas` topic, creating it with the broker's default `cleanup.policy=delete`
instead of the `compact` policy Schema Registry's own explicit init logic would have used —
causing Schema Registry to then fail outright on its own subsequent restart
(`StoreInitializationException: ... Expected cleanup.policy to be 'compact' but it is delete`).
**Fix:** Added `KAFKA_LOG_DIRS: /var/lib/kafka/data` to `kafka/docker-compose.yml`, explicitly
pointing the broker at the mounted volume instead of relying on an unverified default. Deleted
the wrongly-configured `_schemas` topic and let Schema Registry recreate it correctly via a
clean restart. Re-ran `kafka/create_topics.py` and `kafka/register_schemas.py` (both idempotent,
by design) to restore the 10 topics and 18 subjects — same IDs 1-18 came back since content was
byte-identical. **Verified the actual fix, not just the symptom**: restarted the Kafka container
again afterward and confirmed all 10 topics and 18 subjects survived that cycle, plus a full
`pytest tests/ -q` (144 passed, 2 skipped) and a schema-subject-count check.
**Status:** Fixed. No real data was lost — Phase 4/5's topics/schemas contained no
application-meaningful message history yet, only the structural provisioning this phase's own
scripts recreate from source deterministically.

## 2026-09-25 — confluent-kafka's schema_registry submodule missing declared dependencies

**Phase:** 4 — Kafka + Schema Registry
**Symptom:** `pip install confluent-kafka` succeeded, but importing
`confluent_kafka.schema_registry` raised `ModuleNotFoundError: No module named 'authlib'`, and
after installing that, `ModuleNotFoundError: No module named 'cachetools'` next.
**Root cause:** `confluent-kafka` 2.15.1's `schema_registry` submodule imports `authlib`
(OAuth2 client support) and `cachetools` (schema/subject caching) unconditionally, but the bare
`pip install confluent-kafka` doesn't pull either in as a dependency — they're only declared
under the package's `schema-registry` extra.
**Fix:** `requirements.txt` changed from `confluent-kafka>=2.3,<3.0` to
`confluent-kafka[schema-registry]>=2.3,<3.0`, which installs `authlib`, `cachetools`, and their
transitive dependencies correctly in one step.
**Status:** Fixed.

## 2026-09-25 — Phase 2c frontend type errors: missing event type + stale ProductOut stub

**Phase:** 2c — Catalog & Commerce Enhancements
**Symptom:** `npm run build` (`tsc -b`) failed with two errors after wiring Buy Now and the new
`ProductOut` fields: (1) `trackEvent("buy_now_clicked", ...)` in `ProductDetail.tsx` rejected —
`"buy_now_clicked"` wasn't a member of `ClientEventType`; (2) `Wishlist.tsx`'s hand-built
`ProductOut` object (adapting `WishlistItemOut` to the shared `ProductCard`'s prop shape) was
missing `description`/`image_url`/`average_rating`/`review_count`.
**Root cause:** (1) `web/src/lib/analytics.ts` had `buy_now_clicked` explicitly omitted from
the union with a comment noting "no Buy Now UI exists yet" — true when written in Phase 3b, now
stale since Phase 2c adds that UI. (2) `Wishlist.tsx` predates the four new `ProductOut` fields
added in this phase and manually constructs a partial stand-in object rather than fetching real
`ProductOut`s, so the type checker correctly flagged the new required fields as missing.
**Fix:** Added `buy_now_clicked` to `ClientEventType`. Added the four missing fields to
`Wishlist.tsx`'s adapter object (`description: null, image_url: null, average_rating: null,
review_count: 0` — all correct fallbacks since `WishlistItemOut` doesn't carry any of them).
**Status:** Fixed.

## 2026-09-25 — SAWarning "transaction already deassociated" on a mid-test rollback (investigated, not a bug)

**Phase:** 2c — Catalog & Commerce Enhancements
**Symptom:** `tests/app/test_reviews.py::test_duplicate_review_by_same_user_rejected` (first
real test to trigger a genuine DB constraint violation mid-test, flush → `IntegrityError` →
`db.rollback()`, followed by more session activity) produces `SAWarning: transaction already
deassociated from connection` at test teardown (`outer_transaction.rollback()` in
`tests/app/conftest.py`).
**Investigation:** Reproduced in an isolated script completely outside the app/FastAPI (plain
SQLAlchemy session using the same SAVEPOINT-restart-listener recipe as
`tests/app/conftest.py`), confirming it's a session/nested-transaction bookkeeping quirk in
that recipe itself, not anything specific to the reviews endpoint. Checked the actual
correctness question directly: does the outer rollback still discard the data despite the
warning? Queried Postgres after the repro ran — the row was **not** present, i.e. the rollback
worked correctly. The warning is SQLAlchemy being noisy about a `SessionTransaction` wrapper
object's internal accounting across repeated nested-transaction end/restart cycles, not a sign
that test isolation is actually broken.
**Fix:** None applied — verified harmless. Noted here so a future session doesn't re-diagnose
the same warning from scratch or assume it indicates a real isolation bug.
**Status:** Won't Fix (confirmed benign).

## 2026-09-24 — BackgroundTasks scheduled before a DomainError are silently dropped

**Phase:** 3a — Behavioral event contracts
**Symptom:** `order_cancel_clicked` was designed to fire "on request receipt, independent of
whether cancellation ultimately succeeds" (e.g. cancelling an already-cancelled order should
still emit the click). It didn't — a test asserting the event fired on a failing second-cancel
attempt caught 0 emitted events instead of 1.
**Root cause:** `app/routers/orders.py`'s `cancel_order_endpoint` scheduled the event via
`background_tasks.add_task(...)` *before* calling `cancel_order()`, which can raise a
`ConflictError`. FastAPI only attaches a request's accumulated `BackgroundTasks` to the
`Response` object the endpoint function itself returns. When an exception propagates out
instead, `app/main.py`'s `handle_domain_error` exception handler builds a brand-new
`JSONResponse` from scratch — which has no knowledge of the tasks scheduled on the original
(discarded) `BackgroundTasks` instance, so they never run. This applies to any endpoint that
schedules a background task and can still raise afterward — currently only this one.
**Fix:** Changed `cancel_order_endpoint` to call `get_producer().emit(...)` synchronously
instead of via `BackgroundTasks`, since `emit()` already guarantees it can't raise (internal
try/except) and the event must survive the exception path regardless. Left every other
event-emission call site on `BackgroundTasks` as-is, since none of them schedule a task before
a possible subsequent exception in the same request.
**Status:** Fixed.

## 2026-09-24 — unstyled raw `<button>` elements showed default browser chrome

**Phase:** 2b — E-commerce frontend
**Symptom:** The header's "Sign in" link (and any other ad-hoc `<button>` not using the
dedicated `Button` component) rendered with a visible default browser border/box, clashing
with the rest of the design. Found via Playwright screenshot of the Home page, not by
`tsc`/`lint`/build — all passed clean since this is a pure visual defect.
**Root cause:** `styles/global.css` reset `font-family`/`color` on `button` but never reset
`background`/`border`/`padding`/`appearance`, so any raw `<button>` fell back to native
browser button styling unless its own CSS module happened to override it.
**Fix:** Added a proper global `button` reset (`background: none; border: none; padding: 0;
cursor: pointer; appearance: none; ...`) in `styles/global.css`, so every button starts
unstyled unless a component explicitly styles it.
**Status:** Fixed.

## 2026-09-24 — toast notifications could cover the cart drawer's checkout button

**Phase:** 2b — E-commerce frontend
**Symptom:** With the cart drawer open, an "Added to bag" toast appeared directly on top of
the drawer's "Checkout" button, since both were anchored `fixed bottom-right`. Found via
Playwright screenshot of the cart-drawer state.
**Root cause:** `ToastStack` and `CartDrawer` both claimed the same screen corner with no
awareness of each other.
**Fix:** Moved the toast stack to bottom-left (`components/ui/ToastStack.module.css`) and
flipped its exit-slide direction to match (`lib/motion.ts`); the cart drawer stays
bottom-right. Simpler and more robust than trying to coordinate z-index/positioning between
two otherwise-independent components.
**Status:** Fixed.

## 2026-09-24 — blank query-string filter params 422'd instead of being ignored

**Phase:** 2a — E-commerce backend API
**Symptom:** `GET /products?category_id=&min_price=` returned 422 Unprocessable Entity
(UUID/Decimal parse errors) instead of treating the blank values as "no filter." Found via
the plan's manual smoke-test step against the running dev server (`uvicorn` + curl), not by
the automated test suite — every existing test either omitted the param or passed a real
value, never an empty string.
**Root cause:** FastAPI/Pydantic attempts to parse any *present* query param against its
declared type (`uuid.UUID | None`, `Decimal | None`); an empty string is present, so it hits
UUID/Decimal parsing rather than the "absent → None" default path. A real frontend `<select>`
for "all categories" (Phase 2b) would naturally submit `category_id=`, not omit the param.
**Fix:** `app/routers/catalog.py` — added an `Annotated[..., BeforeValidator]` (`OptionalUUID`,
`OptionalDecimal`) that coerces `""` to `None` before type validation for `category_id`,
`min_price`, `max_price`; changed the `brand` filter check from `is not None` to a truthy
check so `brand=""` is likewise treated as unset. Regression test added:
`tests/app/test_catalog.py::test_products_blank_query_params_treated_as_unset`.
**Status:** Fixed.
