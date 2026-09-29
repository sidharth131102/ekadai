# Current State

Living snapshot — always describes what's actually built and runnable *right now*, not
aspiration. Rewritten at the end of each session/phase. Read this first when picking the
project back up.

**Last updated:** 2026-09-29 (restart session done: Gold verified, observability live, app
deployed to Vercel + VM API, Power BI working live, code on GitHub. See "Restart session
results" at the end.)

**Deadline:** Azure free credits (~₹18k) expire **2026-10-07** — the remaining phases need to
land before then; the user asked to move fast.

## What's built and working

- Repo scaffolded, git initialized (no commits yet — nothing has been committed per standing
  instruction to only commit when asked).
- Tracking docs in place: this file, `roadmap.md`, `bugs_and_fixes.md`.
- **Phase 1 — PostgreSQL schema**: all 12 tables, Alembic migration `8f8d545f97fa`, 7
  categories / 43 products seeded, `tests/db` (12 tests) passing.
- **Phase 2a — E-commerce backend API (FastAPI)**: full auth/catalog/cart/wishlist/checkout/
  orders surface, order-creation transaction + promotion engine.
- **Phase 2b — E-commerce frontend (React + Vite + TS)**: "Modern Print Catalog" aesthetic,
  Framer Motion throughout, all 11 pages.
- **Phase 3a — Behavioral event contracts + server-side producer wiring**: all 18 Avro
  schemas (`events/schemas/`), producer library + `LoggingTransport`, 10 server-emitted event
  types wired into existing endpoints.
- **Phase 3b — Client-emitted events, verified end-to-end:**
  - Backend: `POST /events` (`app/routers/events.py`) — optional-auth ingestion endpoint for
    the 8 client-emitted event types. Client sends only `event_type` + `event_timestamp`
    (epoch ms, captured in-browser) + `payload`; the backend fills in `event_id`,
    `context.user_id` (from an optional JWT — anonymous submissions get `null`),
    `context.session_id` (from a new `X-Session-Id` header), and `device.*` (parsed
    server-side from `User-Agent` by the new dependency-free `app/user_agent.py`). Rejects
    (422/404) unknown event types and anything in the 10 server-only types — a client can't
    forge `order_created` through this endpoint. Uses a new `EventProducer.emit_strict()`
    (`events/producer.py`) that *raises* instead of swallowing, so a malformed client payload
    surfaces as a real 4xx rather than vanishing silently — the opposite of every internal
    `BackgroundTasks` call site, which still uses the safe `emit()`.
  - **Retrofit**: `app/deps.py` gained `get_optional_current_user`, `get_session_id`,
    `get_device_info` — and all 10 already-wired Phase 3a server events (in `auth.py`,
    `cart.py`, `wishlist.py`, `checkout.py`, `orders.py`) now attach real `session_id`/
    `device` too, not just the new 8. Confirmed via a spot-check test
    (`test_register_with_session_header_carries_session_id`).
  - Frontend: `lib/session.ts` (per-tab UUID in `sessionStorage`), `api/client.ts` now sends
    `X-Session-Id` on every request, `lib/analytics.ts` (`trackEvent`, fire-and-forget),
    `lib/useDebouncedValue.ts`, `lib/usePageView.ts`. **7 of 8 client event types wired**:
    `page_view` (8 pages — Home/ProductListing/ProductDetail/Cart/Checkout/Wishlist/Orders/
    OrderDetail/Profile; Login/Register intentionally excluded, not in §30's page-type enum),
    `product_view` (ProductDetail), `wishlist_view` (Wishlist), `order_viewed` (OrderDetail),
    `search` (`ProductListing`, debounced 600ms — not per keystroke, per §30), `filter_applied`
    (`ProductListing`, category/availability immediate + price debounced 500ms, one event
    carrying the array of all active filters), `sort_applied` (`ProductListing`, immediate,
    skips the initial-mount default so it only fires on an actual user choice).
    **`buy_now_clicked` stays unwired** — no "Buy Now" UI feature exists (only "Add to bag"),
    confirmed again as an intentional, documented gap, not an oversight.
  - `tests/app/test_events_endpoint.py` (9 tests: valid submission enriched correctly,
    anonymous submission, session-id capture, missing-session-id rejection for
    session-keyed types, device parsing from a real UA string, server-only type rejected,
    unknown type rejected, malformed payload rejected, array-of-filters payload accepted).
    **125 passed, 2 skipped** across the whole backend suite (unchanged skip count/reasons
    from Phase 3a).
  - `npm run build` / `npm run lint` clean — no new warnings versus Phase 2b/3a's baseline.
  - **Manually verified via a real headless-browser walkthrough** (Playwright, temporary,
    `--no-save`): register → browse with a search + category filter + sort change → view a
    product → view wishlist → add to cart → checkout → view the resulting order. **Zero
    console/page errors.** Inspected `var/events.log` afterward: all 7 wired client event
    types landed with correct topics/keys/payloads, and every event in the session — the 10
    server ones included — carried the *same* non-null `session_id` throughout, confirming
    the header/session persistence actually works across full-page navigation cycles.
  - One transient observation, not a bug: `order_viewed` (and other page-mount events) fired
    more than once per visit during the `npm run dev` walkthrough — this is React 18+'s
    `<StrictMode>` (wraps the app in `main.tsx`) intentionally double-invoking effects in
    development builds only; it's stripped automatically in production builds. No code change
    made — "fixing" it would mean fighting React's own dev-mode safety net for a cosmetic,
    dev-only effect.

- **Phase 2c — Catalog & commerce enhancements, verified end-to-end:** triggered by direct
  user feedback after actually using the running frontend: no product images, no descriptions,
  no reviews, no Buy Now, and prices that read as USD-sized when they were always INR values.
  - **Currency fix**: `app/config.py`'s `default_currency` → `"INR"`; `web/src/lib/format.ts`
    now formats with `en-IN`/`INR` (locale keyed off currency code). No price data changed —
    the seeded numbers were always sensible ₹ retail prices, just mislabeled as USD.
  - **Product images + descriptions**: new nullable `description`/`image_url` columns on
    `products` (migration `166965dbced1`, first schema change since Phase 1). Seeded with real
    written copy per product and deterministic Picsum Photos URLs (seeded by product slug, so
    each product always gets the same photo). Frontend: new `ProductVisual` component — real
    `<img>` when `image_url` is present, falling back to the Phase 2b swatch design otherwise;
    used in both `ProductCard` and `ProductDetail`.
  - **Reviews subsystem**: new `reviews` table (not CDC-enabled — same precedent as
    cart/wishlist/promotions/addresses, not in the locked §12 list). `user_id` nullable +
    `reviewer_name` snapshot string (mirrors the `orders.shipping_address_*` snapshot pattern) —
    seeded reviews are truthfully not tied to real accounts, no fake user credentials invented.
    `rating INTEGER CHECK (1-5)`; partial `UNIQUE(product_id, user_id) WHERE user_id IS NOT
    NULL` stops a real user reviewing the same product twice without capping seed review count.
    Average rating / review count computed at query time via a join+aggregate subquery, never
    denormalized onto `products` (same reasoning as §16's existing derived-field stance).
    **User explicitly chose to seed sample reviews** (over shipping empty or skipping the
    feature) when asked directly about the tension with the spec's anti-fabrication principle —
    129 deterministic reviews seeded (`db/seed/review_generator.py`, `random.Random(product_name)`,
    weighted 5/4/3/2-star templates). `GET/POST /products/{id}/reviews`
    (`app/routers/reviews.py`) — list is optional-auth (computes `is_own` per review), submit
    requires auth, duplicate-review attempt → 409.
  - **Rating sort/filter**: closes the gap Phase 2a explicitly flagged ("no ratings data exists
    anywhere in the schema"). `GET /products` gained `sort=rating` (coalesces unreviewed
    products to sort last regardless of direction) and `min_rating`/`max_rating` filters, joined
    against the same rating-aggregate subquery. Frontend `FilterPanel` gained a rating `<select>`
    and a "Rating" sort option.
  - **Buy Now**: a genuine backend bypass of the cart, not add-to-cart-then-checkout (which
    would sweep a user's unrelated existing cart items into the buy-now order).
    `app/services/orders.py` refactored around a shared `RequestedLine` abstraction — pricing
    (promotion resolution + discount math) is source-agnostic; when a `buy_now` line is passed,
    `build_checkout_snapshot`/`create_order` skip cart lookup/locking entirely (`cart: Cart |
    None = None`), so an in-flight buy-now purchase can't read, lock, or mutate the user's cart.
    `POST /checkout/start` and `POST /orders` both accept an optional `{product_id, quantity}`
    body; still no persisted `checkouts` table (§9) — both calls re-validate fresh from the DB.
    `checkout_started`'s Avro schema `cart_id` field made nullable to match (regenerated
    `.avsc`). Frontend: "Buy now" button on `ProductDetail` fires `buy_now_clicked` (unwired
    since Phase 3a, now wired) and navigates to `/checkout` with `{buyNowProduct,
    buyNowQuantity}` in router state; `Checkout.tsx` branches its item-preview and API calls on
    whether buy-now state is present, otherwise behaves exactly as before.
  - `tests/app/test_reviews.py` (7 tests), `TestRatingAggregation` in `test_catalog.py` (4
    tests), `tests/app/test_buy_now.py` (8 tests, including
    `test_buy_now_does_not_touch_existing_cart` — adds a second product to cart, buys a
    *different* product via buy-now, asserts the cart is unchanged afterward). **144 passed, 2
    skipped** across the whole backend suite (up from 125 passed in Phase 3b).
  - `npm run build` / `npm run lint` clean (two pre-existing TS errors surfaced and fixed along
    the way: `ClientEventType` was missing `buy_now_clicked`; `Wishlist.tsx`'s hand-built
    `ProductOut` stub was missing the four new fields).
  - **Manually verified via a real headless-browser Playwright walkthrough**: registered a
    fresh user, confirmed 12 real product images load (`naturalWidth: 640`, not broken-image
    icons) and descriptions/ratings render on both listing and detail pages, filtered by
    `min_rating=4` and sorted by rating, submitted a review and watched it appear immediately
    with a "You" badge (form then correctly hides with "You've already reviewed this
    product."), added one product to cart, then bought a *different* product via Buy Now end to
    end (address → review → confirm) — **confirmed via a direct authenticated `GET /cart` call
    before and after that the original cart item was completely untouched by the buy-now
    purchase.**

- **Phase 4 — Kafka + Schema Registry, local, verified end-to-end:** built while the user
  worked on generating real product images to swap in. Deploying this stack to the real Azure
  B2ms VM is still deferred (recorded since Phase 3) — this phase builds and verifies the exact
  local equivalent via Docker Compose.
  - **Broker**: `kafka/docker-compose.yml` — `apache/kafka:3.8.0`, KRaft mode, single combined
    broker+controller, no ZooKeeper (§37), fixed `CLUSTER_ID` so restarts don't reformat
    storage, dual listeners (`PLAINTEXT` for the compose network, `PLAINTEXT_HOST` mapped to
    `localhost:29092` for the FastAPI app running on the host), 7-day retention
    (`KAFKA_LOG_RETENTION_HOURS=168`). **Schema Registry**: `confluentinc/cp-schema-registry:7.6.1`
    on port 8081, global compatibility default `BACKWARD` (§41).
  - **Topics**: `kafka/create_topics.py` — idempotent, reads topic names from
    `events.registry.EVENT_TYPES` (the existing single source of truth) and creates exactly the
    10 topics from §38 with the exact partition counts from §39 (38 partitions total, RF 1).
    Verified via `AdminClient.list_topics()` — every count matches exactly; re-run confirmed
    idempotent (no errors, no changes).
  - **Schemas**: `kafka/register_schemas.py` — idempotent, registers all 18 `.avsc` files (the
    real contract artifacts, not a re-derived representation) as individual subjects using
    `TopicRecordNameStrategy` (§41): `{topic}-{namespace}.{record_name}`, e.g.
    `user-events-ekadai.events.user.UserRegistered`. Verified: 18 subjects registered with
    sequential schema IDs 1-18; re-run returned identical IDs (confirmed idempotent,
    byte-identical content doesn't create new versions); `GET /config` confirms `BACKWARD`
    globally, individual subjects correctly inherit it rather than overriding.
  - **`KafkaAvroTransport`** (`events/transports/kafka_avro_transport.py`): new implementation
    of the existing `EventTransport` protocol (`events/transports/base.py`) — zero changes to
    `events/producer.py` or any router, which is exactly what that protocol was designed for
    back in Phase 3a. Wire format is Confluent's standard (magic byte `0x00` + 4-byte
    big-endian schema ID + Avro binary body via `fastavro.schemaless_writer`), serialized
    against the *same* fastavro-parsed schema already used for validation — no second Avro
    representation. Schema IDs resolved once per event type via
    `SchemaRegistryClient.register_schema` (idempotent) and cached in memory. Delivery failures
    are logged, never raised, matching `emit()`'s existing contract.
  - **Wiring**: `app/config.py` gained `event_transport` (`"logging"` default — a fresh clone
    or the test suite never requires Kafka), `kafka_bootstrap_servers`,
    `schema_registry_url`. `app/main.py` gained a `lifespan` context manager (didn't have one
    before) that swaps in `KafkaAvroTransport` via `events.producer.set_transport()` only when
    `EVENT_TRANSPORT=kafka`, and flushes the producer on shutdown. Confirmed safe against
    `tests/app/conftest.py`'s fixture order — full suite still **144 passed, 2 skipped**,
    unchanged, both before and after standing up the real Kafka stack.
  - **Manually verified end-to-end**: ran a second backend instance with
    `EVENT_TRANSPORT=kafka`, drove a real register → add-to-cart → checkout → order flow
    through it, then consumed the resulting messages back from `user-events`, `cart-events`,
    `checkout-events`, and `order-events` with a throwaway consumer script. Confirmed for every
    message: correct magic byte, correct schema ID, correct topic, correct partition key
    (matching the entity ID — `cart_id` for `add_to_cart`, `checkout_id` for
    `checkout_started`, `order_id` for `order_created`, `user_id` for `user_registered`), and
    the Avro `decimal` logical type round-tripping as an exact `Decimal` (e.g.
    `gross_merchandise_value: Decimal('1799.00')`), not a float. The always-on dev server (port
    8000, default `EVENT_TRANSPORT=logging`) was untouched throughout and confirmed still
    healthy afterward.
  - One real dependency gap hit and fixed during implementation:
    `confluent-kafka[schema-registry]>=2.3,<3.0`'s schema-registry submodule imports `authlib`
    and `cachetools` for OAuth/caching support without declaring them as install-time
    dependencies in the base extra — installing with the `[schema-registry]` extra (rather than
    bare `confluent-kafka`) pulls in everything needed. `requirements.txt` updated accordingly.
  - `kafka` and `schema-registry` containers now run persistently alongside `ekadai-postgres`
    (same `unless-stopped` pattern) — no code changes needed to keep them running between
    sessions.

- **Phase 5 — Debezium + PostgreSQL CDC, local, verified end-to-end:** built directly after
  Phase 4 at the user's request ("let's focus on the next build now"). Wires real Postgres
  change data capture into the 5 `cdc-*` topics that already existed from Phase 4. **No
  application code changed in this phase** — purely Postgres WAL → Debezium → Kafka.
  - **Postgres**: `db/docker-compose.yml`'s `postgres` service now runs with
    `wal_level=logical` (`max_wal_senders`/`max_replication_slots` raised to 10) — required a
    container restart, data preserved via the existing `pgdata` volume, confirmed via a health
    check + `SELECT count(*) FROM products` immediately after. A dedicated `debezium` role
    (`debezium/setup_postgres.py`, idempotent) — `LOGIN REPLICATION`, `CREATE` on the database,
    and **ownership** (not just `SELECT`) of exactly the 5 CDC tables
    (`users`/`products`/`categories`/`orders`/`order_items`) — both grants turned out to be
    hard Postgres requirements for `CREATE PUBLICATION`, discovered from two real connector
    startup failures, not anticipated at design time (see `bugs_and_fixes.md`). Ownership
    transfer was flagged to and explicitly confirmed by the user before running, since it
    modifies live application table metadata; verified afterward that `ekadai` (a superuser)
    keeps full access regardless, via a live health check and a full test-suite run.
  - **Debezium Connect**: `debezium/Dockerfile` (`debezium/connect:2.7.3.Final` +
    Confluent's `kafka-connect-avro-converter` installed by direct JAR download, confirmed
    working — the base image's plugin directory is writable by its default user, no `USER
    root` needed) + `debezium/docker-compose.yml`, reaching Kafka/Schema Registry/Postgres all
    via `host.docker.internal`. This required a **new Kafka listener**
    (`kafka/docker-compose.yml`'s `PLAINTEXT_DOCKER`, port 29093, advertised as
    `host.docker.internal`) — the existing `PLAINTEXT_HOST` listener is advertised as
    `localhost`, which only resolves correctly for a process actually on the host, not from
    inside another container (Debezium's own reconnect-after-metadata attempt was failing
    against it before this fix).
  - **One connector** (`debezium/register_connector.py`, idempotent — `PUT` by name) covering
    all 5 tables: `plugin.name=pgoutput` (native, §44), `publication.autocreate.mode=filtered`
    (no manual `CREATE PUBLICATION`), `snapshot.mode=initial` (§49). Five chained `RegexRouter`
    transforms rewrite Debezium's default topic name to the exact pre-existing Phase 4 topic
    (`cdc-order-items` needs the hyphen, the table is `order_items` with an underscore).
    `message.key.columns=public.order_items:order_id` overrides that one table's outgoing
    Kafka key from its actual primary key (`order_item_id`) to `order_id`, matching §39's
    partition-key table (preserve per-order ordering) — the other 4 tables' primary keys
    already matched §39 as-is.
  - **Manually verified end-to-end**: connector + task both `RUNNING`
    (`GET /connectors/ekadai-postgres-cdc/status`); confirmed the filtered publication
    (`puballtables=false`) covers exactly the 5 tables via `pg_publication_tables`, and the
    `debezium_ekadai` replication slot is `active=true` via `pg_replication_slots`. **Initial
    snapshot**: consumed and Avro-decoded every message from all 5 `cdc-*` topics — message
    counts matched live row counts exactly (13 users, 43 products, 7 categories, 7 orders, 7
    order_items), `op="r"` with `source.snapshot` populated on every row (§46 snapshot metadata
    preserved). **Live streaming**: made a real `UPDATE` on a product's price directly in
    Postgres and placed a real order through the running API, then confirmed fresh
    non-snapshot messages landed within seconds — `cdc-products` showed `op="u"` with the new
    price in `after`, `cdc-orders` showed `op="c"` with the new order, and critically
    `cdc-order-items`'s message key was confirmed to be the **order_id**, not the
    order_item_id, proving the key override works for live inserts too, not just the snapshot.
    `pytest tests/ -q` stayed at **144 passed, 2 skipped** throughout (no app code touched).
  - Two real bugs hit and fixed during implementation, both logged in `bugs_and_fixes.md` in
    detail: (1) the Kafka container's actual default log directory (`/tmp/kafka-logs`) didn't
    match where the "persistent" volume was mounted (`/var/lib/kafka/data`), so a routine
    container recreate silently wiped all 10 Phase 4 topics and schemas — fixed with an
    explicit `KAFKA_LOG_DIRS` env var, and **actually verified** by restarting the container
    again afterward and confirming everything survives that cycle now; (2) the publication
    ownership requirement above.

## New implementation-level conventions established in Phase 3b (not spec-locked, decided here)

- `X-Session-Id`: per-tab, `sessionStorage`-backed, generated once via `crypto.randomUUID()`.
- Session-keyed client event types (`page_view`, `search`, `filter_applied`, `sort_applied`,
  `product_view`, `wishlist_view`) *require* the header — missing it is a hard 422, not a
  silent null-key fallback, since the frontend now always sends it.
- `POST /events` batches nothing — one event per request. Deliberate scope call: call sites
  here are low-frequency (page mounts, debounced typing), not worth a client-side queue yet.

## What's deliberately not built yet

Review moderation/reporting, editing/deleting a submitted review, real product photography
(Picsum Photos placeholder stands in for most categories — a soft external dependency, unlike
the self-hosted fonts; Electronics now has real generated photos, see below). Event
batching/beacon-on-unload. Phases 8–16 (Silver CDC/SCD2 onward, Gold, observability, Power BI).
(Cloud infrastructure — Supabase, the Azure VM, Databricks — all exists now; see below.)

**Product images, in progress (user-driven, not a phase):** the user is generating real product
photos category by category and dropping them in `web/public/<slug>.jpg`. All 7 Electronics
products are done and verified live in the browser. Workflow to add more:
`db/seed/data/products.json`'s `image_url` gets updated to the local path, then
`python -m db.seed.sync_images` (new, idempotent — syncs just that field onto already-seeded DB
rows, since `run_seed.py`'s backfill only fires when a row has no image at all) pushes it onto
the live DB. No migration or reseed needed.

## Cloud migration (done — kept here for the how/why)

The user chose real Azure Databricks on their free credits, so the full chain moved to the
cloud: Postgres → Supabase, Kafka+Debezium → an Azure VM, then Databricks for the lakehouse.

- **Azure VM: up and running.** Provisioning `Standard_B2ms` (and every "legacy-generation"
  equivalent — `D2s_v3`, `B2as_v2`) failed identically across three regions with a misleading
  `SkuNotAvailable: Capacity Restrictions` CLI error. The *real* cause, only visible through the
  Azure Portal's VM-creation UI: this subscription's quota for **legacy VM generations is
  permanently non-adjustable** ("Additional quota isn't available for this family" — confirmed
  via the Quotas blade, `Standard DSv3 Family` shown as "Legacy - migration recommended,
  Adjustable: No"). Fix: use a **current-generation** size instead —
  `Standard_D2ns_v6` (2 vCPU, 8 GiB, no local NVMe needed) deployed successfully on the first
  try. VM: `ekadai-vm`, resource group `ekadai-rg`, **East US**, public IP `20.102.92.77`,
  SSH as `ekadai` with the key at `~/.ssh/ekadai_azure_vm{,.pub}`. NSG (`ekadai-vm-nsg`) scoped
  to the current dev IP for SSH (22) and Kafka/Connect/Schema-Registry/Postgres ports
  (29092/8081/8083/5432) — **must be updated if the dev machine's public IP changes**
  (`az network nsg rule update ... --source-address-prefixes <new-ip>/32`).
- **IPv6: added and confirmed working on the VM.** The Portal's quick-create didn't set up
  IPv6 by default — added an IPv6 address space to the VNet/subnet + a Standard IPv6 public IP
  + a second IP config on the VM's NIC, then restarted the VM. Confirmed via `curl -6` to a
  real IPv6-only endpoint (`200 OK`) and, more importantly, a direct `psql` connection *from
  inside the VM* to Supabase's IPv6-only direct-connection endpoint — succeeded. (This
  machine's own network still has no IPv6 at all — confirmed dead on both a mobile hotspot and
  home WiFi — so this was VM-side only.)
- **Postgres: migrated to Supabase, verified end-to-end.** Per the user's call ("if [VM IPv6]
  works then we can keep supabase"), it worked, so Supabase stays. Two connection strings are
  now in play, and this split isn't a workaround — it's the correct production architecture
  regardless of where the app is ever hosted:
  - **App → Supabase session pooler** (`aws-0-ap-southeast-1.pooler.supabase.com:5432`, IPv4,
    reachable from anywhere) — this is `DATABASE_URL` in `.env` now. `TEST_DATABASE_URL` is
    untouched (still local Postgres — tests stay fast/network-independent).
  - **Debezium → Supabase direct connection** (`db.mbqbyfrajzaaielorful.supabase.co:5432`,
    IPv6-only) — logical replication fundamentally cannot go through a pooler, in any
    environment, forever; this is the one thing that will always need the direct connection.
  - `alembic upgrade head` and `db/seed/run_seed.py` both run cleanly against Supabase (43
    products, 7 categories, 129 reviews seeded). Dev server restarted against it, confirmed live
    (`GET /products` round-trips real data). Full `pytest tests/ -q` still 144 passed, 2 skipped
    (uses `TEST_DATABASE_URL`, unaffected).
  - `debezium/setup_postgres.py` updated and re-verified against Supabase specifically: (1) a
    hardcoded `GRANT CREATE ON DATABASE ekadai` was a latent bug for any non-local target — now
    uses `CURRENT_DATABASE()`; (2) Supabase's `postgres` role isn't a true superuser (unlike
    self-hosted Postgres), so `ALTER TABLE ... OWNER TO debezium` needed the connecting role
    granted membership in `debezium` first (`GRANT debezium TO CURRENT_USER`), and modern
    Postgres additionally requires the new owner to hold `CREATE` (not just `USAGE`) on the
    schema before an ownership transfer succeeds — both now handled automatically, script is
    portable across self-hosted and managed Postgres without config flags. Verified via
    `pg_tables.tableowner` on Supabase and a clean idempotent re-run.
  - `db/alembic/env.py` got a real fix along the way: `ConfigParser` (which
    `set_main_option` writes through) treats a bare `%` as the start of an interpolation
    reference, which broke on the percent-encoded `%40` in the Supabase password — now escaped
    to `%%` before being set.
- **Kafka + Schema Registry + Debezium: deployed on the VM, verified end-to-end.** New
  `azure/vm-stack/` (`docker-compose.yml` + `debezium.Dockerfile`) combines all three services
  into one Compose project on the VM — simpler than the local dev split across `kafka/` and
  `debezium/`, since everything shares one Docker network directly (container DNS names like
  `kafka:9092`/`schema-registry:8081`) with no `host.docker.internal` bridging needed (that
  existed purely for Windows Docker Desktop's host/container split). Docker installed via
  `get.docker.com`. All 3 containers healthy (`ekadai-kafka`, `ekadai-schema-registry`,
  `ekadai-debezium-connect`).
  - **A second IPv6 layer surfaced and got fixed**: the VM host having real IPv6 doesn't mean
    its Docker *containers* do — confirmed via `ip -6 addr show` inside the Connect container
    (loopback only). Docker's daemon-level IPv6 config only covers the default bridge network;
    Compose's own project network needs `enable_ipv6: true` declared explicitly (now in
    `azure/vm-stack/docker-compose.yml`), on a subnet distinct from the daemon's own (`fd00:
    1234:567{8,9}::/64` respectively — reusing the same range hit a real "pool overlap" error).
    Confirmed fixed via `curl -6` from inside the container succeeding after the change.
  - `kafka/create_topics.py` and `kafka/register_schemas.py` reran cleanly against the VM
    (`KAFKA_BOOTSTRAP_SERVERS=20.102.92.77:29092`, `SCHEMA_REGISTRY_URL=http://20.102.92.77:8081`
    — both scripts already read these from env, no code changes needed) — 10 topics/38
    partitions, 18 subjects, same as every prior verification.
  - `debezium/register_connector.py` made portable via new env vars (`DB_HOSTNAME`, `DB_NAME`,
    `SCHEMA_REGISTRY_URL_FOR_CONNECTOR` — the last one specifically because Connect resolves
    that URL from *inside its own container*, so it must be the container-network name
    `schema-registry:8081`, not whatever host verification scripts use). Registered against
    Supabase's direct connection (`db.mbqbyfrajzaaielorful.supabase.co`, db `postgres`) —
    connector + task both `RUNNING`.
  - **Full pipeline verified live**: publication (`debezium_ekadai_publication`, filtered to
    exactly the 5 tables) and replication slot (`debezium_ekadai`, `pgoutput`) both exist on
    Supabase. Snapshot counts consumed off the VM's Kafka matched Supabase's live row counts
    exactly (43 products, 7 categories, 0 users/orders/order_items — nobody had registered on
    Supabase yet at that point). Then registered a real user **through the local app** (now
    pointed at Supabase via the pooler) and confirmed a fresh `op="c"` event landed on
    `cdc-users` within seconds, with the correct email — the complete chain (local app →
    Supabase → Debezium on the VM → Kafka on the VM → consumed from the local machine) is
    real and working, not just individually-tested pieces.
- Tooling note for next session: Azure CLI's DNS resolution is broken specifically in this
  project's Bash tool (works fine in PowerShell) — run all `az` commands via PowerShell, with
  `$env:Path` refreshed each call (`$env:Path = [System.Environment]::GetEnvironmentVariable...`
  — see recent conversation for the exact snippet) since it doesn't persist between tool calls.
  SCP/SSH to the VM work fine from the Bash tool directly (only `az` itself was affected).

**The cloud migration (Postgres → Supabase, Kafka+Debezium → Azure VM) is now fully done and
verified.** Local Kafka/Debezium/Postgres (Docker Desktop) still exist untouched as a fallback
dev setup, but the app and CDC pipeline now run against the cloud versions by default.

### Phase 6 — Bronze ingestion, real-time, verified end-to-end

**What's running:** one serverless, continuous **Lakeflow Declarative Pipeline**,
`ekadai-bronze` (pipeline id `5d26a480-752f-41b6-9597-c2c8c97c2e1c`), source
`databricks/bronze_pipeline.py`. It streams all 10 Kafka topics from the VM into six Delta
tables in Unity Catalog `ekadai_databricks.bronze`:
- `bronze_events` — the 5 behavioral topics, exactly §51's columns (`raw_payload` = full decoded
  envelope as JSON, plus `event_id`, `event_type`, `schema_version`, `event_timestamp`,
  `kafka_topic/partition/offset/timestamp`, `ingestion_timestamp`).
- `bronze_cdc_users/products/categories/orders/order_items` — one per CDC entity. The spec gives
  no exact Bronze CDC schema, so this repo defined one: full Debezium envelope in `raw_payload`,
  plus `before_json`, `after_json`, `op`, `ts_ms`, `source_lsn`, `source_tx_id`,
  `source_snapshot`, and the same Kafka lineage + `ingestion_timestamp` columns.

Avro decoding: behavioral topics carry several schemas per topic (TopicRecordNameStrategy), so a
UDF reads each message's schema ID from the Confluent wire-format header and resolves it against
Schema Registry. CDC topics use the same header, so one decoder serves both.

**Azure/Databricks resources** (all East US, all in `ekadai-rg`; rebuild with
`databricks/provision.ps1`): Premium workspace `ekadai-databricks`; ADLS Gen2 account
`ekadailake` with `bronze`/`silver`/`gold` containers; access connector
`ekadai-access-connector` (Storage Blob Data Contributor); UC storage credential, external
locations and `bronze`/`silver`/`gold` schemas; NSG rule letting the
`AzureDatabricksServerless.EastUS` service tag reach Kafka (29092) and Schema Registry (8081).

**Verified with real data, not just a running status:**
- Snapshot CDC counts in Bronze match Supabase exactly (43 products, 7 categories).
- Latency, measured by driving a real action through the app and polling Bronze:
  **behavioral event → `bronze_events` in ~26s; Postgres change → `bronze_cdc_users` in ~46s**.
  Both figures include ~5s polling interval and ~10–15s SQL-warehouse query overhead, so actual
  pipeline latency is lower.
- Backend test suite unaffected (no app code changed in this phase).

**How the design evolved (all user decisions, in order):** the approved plan was a cost-first
scheduled micro-batch (every 15 min, ephemeral job clusters). The user then set **real-time
analytics** as the end goal, which requires a continuous stream. Classic clusters couldn't
reliably get VMs in this subscription (stockouts and zero-quota VM families, same as the VM
saga); serverless *jobs* reject infinite triggers outright; serverless *pipelines* support
continuous mode and avoid both problems — so that's what shipped. Table names, columns, topics
and decoding logic stayed identical through every change, per the user's "nothing breaks"
requirement. The superseded jobs and scripts were deleted so the workspace only shows what runs.

**Cost / operations — read before leaving it running:**
- The pipeline is continuous serverless: **it bills the whole time it's running**, not only
  when data arrives. Stop it between work sessions:
  `databricks pipelines stop 5d26a480-752f-41b6-9597-c2c8c97c2e1c`
  and restart with `databricks pipelines start-update 5d26a480-752f-41b6-9597-c2c8c97c2e1c`
  (checkpoints resume from where it stopped — nothing is re-ingested or lost, within Kafka's
  7-day retention).
- **Your public IP changes** (home/mobile connection). When it does, the NSG blocks this
  machine from Kafka and the app's producer silently fails to publish (events are buffered for
  ~5 min, then dropped with delivery errors in the dev-server log). This happened once today.
  Fix: `az network nsg rule update -g ekadai-rg --nsg-name ekadai-vm-nsg -n allow-kafka-broker
  --source-address-prefixes <new-ip>/32` (and the same for rule `SSH`). The pipeline itself is
  unaffected — it reaches Kafka via the serverless service tag.
- For the app to publish to the cloud Kafka, the dev server must run with
  `EVENT_TRANSPORT=kafka KAFKA_BOOTSTRAP_SERVERS=20.102.92.77:29092
  SCHEMA_REGISTRY_URL=http://20.102.92.77:8081` (not in `.env` by default).

**Not done:** Bronze's 90-day retention (§51) isn't enforced yet — a retention/vacuum policy is
still to add (Phase 13 maintenance).

### Phase 7 — Silver events + validation, real-time, verified end-to-end

**What changed in the pipeline:** the same continuous pipeline `ekadai-bronze` now has two
sources — `databricks/bronze_pipeline.py` and `databricks/silver_pipeline.py` — plus the
workspace FILE `silver_rules.py` that the Silver source imports. One always-on compute, no
extra cost. Config value `ekadai.pipeline_version = 0.7.0` stamps every Silver row (§43; no git
commit SHA exists yet since nothing has been committed).

**Bronze hardening (user-approved, additive only):** the Avro decoder never raises now — a
message it can't decode still lands in Bronze with `decode_error` set, instead of stopping the
whole stream. All six Bronze tables gained two columns at the end, `raw_value` (the original
Kafka bytes) and `decode_error`; every existing column is unchanged. Needed one full refresh
(re-read Kafka from `earliest`, no data lost).

**Validation rules** (`databricks/silver_rules.py`): pure Python, no Spark, unit-tested
locally (`tests/databricks/test_silver_rules.py`, 59 tests — every test envelope goes through
the app's real `build_envelope` → Avro encode/decode → Bronze-style JSON). Three error types:
- `MALFORMED` — Bronze couldn't decode it, or it isn't a JSON object.
- `SCHEMA_INVALID` — bad/missing `event_id`/`event_type`/`schema_version`/`event_timestamp`,
  event on the wrong topic, or the topic's partition key (§39) missing.
- `BUSINESS_RULE` — quantities ≤ 0, negative money, `cart_net_value ≠ gross − discount`,
  discount > gross, currency not 3 uppercase letters, empty search, and the §68 filter rules
  (price/rating need a bound with min ≤ max, rating 0–5, price ≥ 0, each filter type populates
  only its own field). One bad filter quarantines the whole event.
`EVENT_ROUTING` mirrors `events/registry.py`; a test fails if they ever drift apart.

**Tables** (all in `ekadai_databricks.silver`):
- `silver_events` — valid events, exactly §54's columns (timestamps as TIMESTAMP, money as
  DECIMAL(18,2)). Written with AUTO CDC keyed on `event_id` (SCD1, sequenced by Kafka
  timestamp/partition/offset) — a duplicate `event_id` can never make a second row, and Phase 9
  can update rows in place. `reference_status`/`reference_errors` (Phase 9) and
  `is_late`/`is_too_late` (Phase 10) are deliberately null until their phases.
- `silver_event_filters` — one row per filter of each valid `filter_applied` event, keyed
  (`event_id`, `filter_index`). `filter_index` isn't in §68's list; it's the filter's position,
  needed to make "one row per filter" idempotent.
- `silver_event_quarantine` — §64 fields, keyed on Kafka topic/partition/offset (a malformed
  message may have no `event_id`). Undecodable messages store `raw_payload` as
  `base64:<original bytes>`, so each quarantine row is self-contained.
- Fields outside §54 (`sort_field`, `page_type`, `wishlist_id`, …) stay in Bronze's
  `raw_payload` only (§53 — no catch-all attributes column).

**Verified with real data:**
- All 17 pre-existing events flowed to `silver_events` (17 rows, 17 distinct ids, 0 null
  timestamps); quarantine empty for normal app traffic. One `checkout_started` row checked
  column by column against its Bronze `raw_payload` — every value matches.
- Injected straight into Kafka on the VM: garbage bytes → Bronze row with
  `decode_error = "ValueError: unexpected magic byte 116"` and quarantine `MALFORMED`, and the
  pipeline kept running (no flow failures in the event log); `add_to_cart` with
  `quantity_added = 0` → `BUSINESS_RULE`; the same envelope sent twice → two Bronze rows, one
  Silver row; `filter_applied` with price + availability → 2 `silver_event_filters` rows; price
  min 9000 > max 100 → `BUSINESS_RULE`.
- Latency, one real `POST /events` through the app: event time → Kafka 2.1s → Bronze 3.6s →
  Silver 7.2s — **13.0s end to end** (measured from the row's own timestamps, not polling).
- Full suite: **203 passed, 2 skipped** (144 backend + 59 Silver-rule tests).

**Operations:** the NSG rule `allow-kafka-broker` currently allows `116.68.102.217/32` (IP
changed again this session). The pipeline has been running continuously since 2026-09-27 and
bills the whole time — see the stop/start commands under Phase 6.

### Phase 8 — Silver CDC + SCD2, real-time, verified end-to-end

**What changed:** a third source in the same continuous pipeline,
`databricks/silver_cdc_pipeline.py` (`pipeline_version` now `0.8.0`), plus
`databricks/silver_views.sql`. No full refresh was needed; the new flows read their Bronze
tables from the start. Both are wired into `databricks/provision.ps1`.

**Tables and views** (all `ekadai_databricks.silver`):
- `silver_cdc_orders` (§69) and `silver_cdc_order_items` (§70): change logs, one row per CDC
  change, exactly the spec columns.
  - `operation` is `INSERT`/`UPDATE`/`DELETE`/`SNAPSHOT`.
  - `change_timestamp` is the DB commit time (`source.ts_ms`).
  - `change_position` is the WAL LSN; `transaction_id` is the Postgres txId.
  - Written with AUTO CDC SCD1 keyed on (id, `change_position`), so a redelivered message can
    never add a row.
- `silver_products_history` / `silver_categories_history` / `silver_users_history`: SCD2 kept
  by AUTO CDC.
  - Sequenced by `struct(change_position, change_timestamp, snapshot)`, so versions are
    ordered by WAL position, not arrival (§47, §92).
  - A DELETE closes the current version (§50).
  - `track_history_column_list` limits new versions to real attribute changes:
    - products: name/category/brand/price/status;
    - categories: name/status;
    - users: city/state/account_status.
  - Everything else (e.g. `updated_at`) updates in place.
  - Users never carry email, password or phone (§73).
- `silver_products` / `silver_categories` / `silver_users` (§71–73) are **Unity Catalog views**
  over the history tables, with exactly the spec columns:
  - `*_version_key` = `xxhash64(id, WAL position)`: deterministic, the same after a rebuild;
  - `valid_from` / `valid_to` = the commit times of the opening and closing changes;
  - `is_current`.
  - A version opened by the initial Debezium snapshot uses `valid_from = created_at`. The
    snapshot proves the row existed from then, and pre-snapshot orders still need a version
    to join to.
  - Zero compute; always as current as the pipeline.
- Parsing is native Spark, with no Python UDF. Debezium's encodings: ISO-string timestamps,
  DATE as days since epoch, decimals as strings. Duplicate (key, LSN) pairs are dropped
  upstream with `dropDuplicatesWithinWatermark` (7 days = Kafka retention). Bronze rows with
  `decode_error` are skipped here and counted in Phase 13.

**Verified with real data:**
- The snapshot matches Bronze exactly: 43 products, 7 categories, 4 users (all current), and
  the change logs = distinct (id, LSN) in Bronze.
- **Real app flow** (register in Kochi → PATCH Chennai → PATCH Mumbai → buy-now order →
  cancel):
  - `silver_users`: 3 versions with contiguous `valid_from`/`valid_to` and only Mumbai current;
  - `silver_cdc_orders`: `INSERT … CONFIRMED` then `UPDATE … CANCELLED` (with
    `cancelled_at`);
  - `silver_cdc_order_items`: the line.
- **Synthetic `cdc-products` messages** for test product `zz-phase8-ooo-test` (id
  `00000000-0000-4000-8000-000000000800`, brand `zz-test`; Gold must exclude it):
  - **out of order**: sent LSN 1, 3, 2 → history 100 → 200 → 300 in LSN order, with 300
    current;
  - **description-only edit** → no new version;
  - **exact-bytes duplicate** of v3 → no new version (5 Bronze messages, 3 versions);
  - **DELETE** → the last version closed and nothing current.
  - The 43 real products are unaffected.
- Duplicate of a real `cdc-orders` message (exact bytes) → 3 Bronze rows, still 2 Silver
  change rows.
- **Latency**: DB commit → Silver SCD2 commit **~23s** at steady state (06:01:44 → 06:02:07).
  About 14s of that is Debezium → Kafka → Bronze. The first sample right after the pipeline
  restart was ~43s (catch-up).

**Replica identity:** the 5 CDC tables on Supabase are now `REPLICA IDENTITY FULL`. The user
ran `python -m debezium.setup_postgres`, since it was blocked for me as a shared-DB change.
UPDATE and DELETE events carry the full old row (§46). Verified with a new order placed and
cancelled through the app: `silver_cdc_orders` shows `status_before = CONFIRMED →
status_after = CANCELLED`. Changes from before this (e.g. order `c3b3ad56-…` above) keep a null
`status_before`.

**App fix found along the way:** see `bugs_and_fixes.md`. The API's DB pool now uses
`pool_pre_ping` + `pool_recycle`, because Supabase's pooler drops idle connections and the
first request after idling 500'd.

**Test data in Silver** (tagged, for Gold to exclude): users `p8-verify-*` / `p8-latency-*` /
`p8-replident-*` emails, orders `c3b3ad56-…` and `556b9cda-…` (both cancelled), the synthetic product above; plus Phase 7's
`p7neg-*` / `p7-latency` events.

### Phase 9 — Reference resolution, streaming and in place, verified end-to-end

**What changed:** only `databricks/silver_pipeline.py` (`pipeline_version` `0.9.0`).
`silver_events.reference_status` / `reference_errors` are now real (§60–63):
- The event's `user_id` (USER), `product_id` (PRODUCT) and `category_id` (CATEGORY) are each
  checked **independently** against what CDC has delivered to Bronze.
- An unknown product never implies an unknown category (§63).
- `reference_errors` looks like `["UNKNOWN_PRODUCT:<id>"]`, or null when everything
  resolves.
- The status is RESOLVED (no references, or all known), UNRESOLVED (all unknown) or
  PARTIALLY_RESOLVED.
- Unresolved events stay in Silver as `VALID` (§60).

**How corrections work (race-free):**
- `silver_events`' AUTO CDC source is a union of (a) new valid events and (b) corrections.
- When a reference first appears in CDC (insert or snapshot), every event referencing it is
  re-derived from `bronze_events` and re-emitted with recomputed status and a higher `_seq`
  revision. AUTO CDC updates the existing row by `event_id`, so there's never a second or
  partial row.
- Existence is looked up in the Bronze CDC tables, the same tables the triggers stream from,
  re-read every micro-batch.
  - An event already in Bronze when its reference lands is fixed by (b).
  - One that lands later is checked by (a), by which time the reference is visible.
- The first design read unresolved rows back from `silver_events`. The pipeline graph rejected
  that as a cycle (a flow can't read its own target), which is why corrections re-derive from
  Bronze (see `bugs_and_fixes.md`).

**`reference_resolution_queue` (§62):** a materialized view in the same pipeline, refreshed
continuously and fully derived, so it can't drift from the data. It has one row per
(reference_type, reference_id) that some event needed before CDC delivered it:
- `first_seen_at` / `last_seen_at`, `affected_event_count`, and `resolved_at` (when the
  reference landed in Bronze);
- `status`:
  - `PENDING`: the reference hasn't arrived;
  - `PROCESSING`: it arrived but events aren't all corrected yet;
  - `RESOLVED`;
  - `FAILED`: pending more than 7 days, with `error_message`;
- `retry_count` = later events that re-checked the id and still missed;
- `last_attempt_at`.

**Verified with real data:**
- `silver_events` was rebuilt: the same 30 ids with an identical checksum; 26 RESOLVED, and
  the 4 UNRESOLVED are exactly the Phase 7 test events with random user/product ids.
- **Event before its reference**:
  - A `product_view` for a not-yet-existing product X (`…000000000900`) landed as
    `UNRESOLVED` with `UNKNOWN_PRODUCT:X`.
  - Then a synthetic `cdc-products` insert for X (`zz-phase9-ref-test`, brand `zz-test`)
    arrived, and the **same row** flipped to `RESOLVED` **~8s** later (06:35:50.2 →
    06:35:58.0), still one row for that event_id.
  - The queue shows X `RESOLVED` with `resolved_at`.
- **§63**: a `page_view` with an unknown product Y (`…000000000901`, never created) and a known
  category → `PARTIALLY_RESOLVED`, with only `UNKNOWN_PRODUCT:Y`. The queue shows Y `PENDING`.
- **Natural cases**: the queue independently found several `user_registered` events that
  reached Silver ~1s before their user's CDC row. All were corrected (`RESOLVED`). That's the
  real-world race this phase exists for.
- **Caveat**: queue rows from before 2026-09-27 16:08 partly reflect the Phase 7 full refresh
  re-ingesting everything at once. Bronze `ingestion_timestamp` was reset then, so some
  "needed before arrival" entries there are an artifact of the replay, not real waits.

**Operational notes:**
- A single-table refresh isn't allowed in continuous mode, so I switched to triggered mode for
  one run and back. The steps are recorded in `provision.ps1`.
- **A Bronze full refresh re-reads Kafka (7-day retention).** Once the initial Debezium
  snapshot (2026-09-26) ages out around 2026-10-03, a Bronze full refresh would lose the
  snapshot rows. Avoid Bronze full refreshes after that, or re-snapshot first.

### Phase 10 — Late data + Airflow replay DAG, verified end-to-end

**Late flags** (`silver_pipeline.py`, `pipeline_version` `1.0.0`):
- `lateness = kafka_timestamp − event_timestamp`.
- `is_late` when above the watermark (10 min); `is_too_late` when above watermark + allowed
  lateness (15 min).
- The thresholds are pipeline config (`ekadai.watermark_minutes`,
  `ekadai.allowed_lateness_minutes`).
- Kafka's append time is used, not Bronze's `ingestion_timestamp`, because a Bronze full refresh
  resets the latter and would make everything look late.
- Too-late events **stay in `silver_events`** (§66).
- The rule for Phase 11/12 Gold: admit an event when `NOT is_too_late`, or when its
  `late_data_replay_queue` row is `PROCESSED`.
- Existing rows were backfilled with a one-table refresh (32 rows, none late).

**Empirical check (§65):** the real lateness distribution, Kafka time − event time, on non-test
traffic:
- Server-stamped events (14): max **0.53s**.
- Client-stamped events (18, browser clock): p50 0.7s, p99 5.6s, max **6.0s**.

10 + 5 min is therefore very generous for this traffic: nothing real is anywhere near late. It's
kept as the spec's starting point, since mobile or offline clients and batch uploads could lag
by minutes. Revisit it with more traffic.

**`ekadai_databricks.silver.late_data_replay_queue` (§67):** a plain Delta table, created and
maintained by the DAG.
- The fields are exactly §67.
- `replay_id = xxhash64(event_id)`, so detection never duplicates.
- It holds ids and metadata only; the payload stays in Bronze.

**Airflow** (`azure/vm-stack/airflow/`):
- `apache/airflow:2.10.5` + the Databricks provider, `airflow standalone` (SQLite), as a
  separate Compose project on `ekadai-vm` with `mem_limit: 2g`. VM memory after start is
  ~3.7 GB free.
- UI: `http://20.102.92.77:8080` (NSG `allow-airflow-ui`, your IP only). User `admin`; get the
  password with
  `ssh ... 'sudo docker exec ekadai-airflow cat /opt/airflow/standalone_admin_password.txt'`.
- Databricks access: a 14-day workspace token (expires **2026-10-13**, id `7133deba…`). It lives
  only in `~/vm-stack/airflow/airflow.env` on the VM (`chmod 600`, gitignored) and was never
  printed or committed.
- **DAG `late_data_replay`** (hourly): `ensure_queue` → `detect` → `replay` → `retention`.
  - `detect` MERGEs too-late Silver events in as `PENDING`.
  - `replay` re-reads the exact event from Bronze by event_id, set-based. If it's present and
    decodable in Bronze and present in Silver → `PROCESSED`; else `FAILED` with
    `retry_count + 1` and `error_message`, retried up to 3 times.
  - `retention` deletes `PROCESSED` rows 30 days after processing (§95).
  - It runs SQL on the serverless SQL warehouse.

**Verified live:**
- Events posted through the app with timestamps 12 and 20 min in the past: `is_late=true /
  is_too_late=false` and `true / true`.
- The DAG (scheduled + manual runs, all tasks green) queued **only** the 20-min event and moved
  it to `PROCESSED` (lateness 1202s, with `reason`).
- Re-runs changed nothing (same `processed_at`).
- A hand-inserted record for a nonexistent event_id → `FAILED` with "event_id not found
  (decodable) in bronze_events", `retry_count` climbing to the cap of 3. The test record was
  deleted afterwards.
- Airflow's health endpoint is reachable from the dev machine.

**Cost changes made this phase:**
- The SQL warehouse auto-stop dropped from 10 min to **1 min**.
- The replay DAG runs **hourly**, not every 15 min. Otherwise the warehouse would idle most of
  the time.
- Exact spend can't be read here: the Azure usage API returns no cost for this credit
  subscription, and Databricks' `system.billing` tables aren't enabled. Check the Azure portal
  credit balance.

### Budget stop (2026-09-29)

Credits: **₹7,978 left of ~₹18k** (expires 2026-10-07). About ₹2k/day was being spent, mostly
by the always-on serverless pipeline. The user asked to stop everything, finish the build, then
restart once. Current state:
- the pipeline is **stopped** and switched to **triggered** mode;
- the SQL warehouse is stopped (auto-stop 1 min);
- the VM `ekadai-vm` is **deallocated**. Its IPs are Standard SKU, i.e. static, so
  20.102.92.77 survives;
- the Airflow DAG `late_data_replay` is paused;
- the local dev API on :8000 still runs with `EVENT_TRANSPORT=kafka`, so anything it emits
  while the VM is down is lost. Don't use it until the VM is back.

### Phases 11–16, built offline (not yet run)

- **Gold** (`databricks/gold_pipeline.py`, 15 materialized views in `ekadai_databricks.gold`):
  - five dimensions, four facts, six aggregates, following §74–91 field lists;
  - deterministic hashed keys, "as of" dimension joins, 30-min sessions, 15-min abandonment,
    cancellations on the cancellation date, and 7-day attribution;
  - the too-late admission rule, and `zz-test` products excluded.
- **Observability** (`databricks/ops_views.sql`, schema `ops`):
  - the pipeline event log published to `ops.pipeline_event_log` (spec change);
  - views `pipeline_runs`, `pipeline_stage_metrics`, `latency_metrics`,
    `data_quality_metrics`, `reference_resolution_status`, `late_replay_status`, `kafka_lag`,
    `cdc_connector_health` and `retention_status`;
  - tables `kafka_offsets`, `cdc_connector_status`, `backfill_audit` and
    `reconciliation_results`.
- **Airflow DAGs** (`azure/vm-stack/airflow/dags/`):
  - `kafka_cdc_health` (every 30 min; Airflow now joins the `vm-stack_default` network and has
    `confluent-kafka` in its image);
  - `backfill_reconcile` (manual; parameters; audit + 8 reconciliation checks; toggles
    continuous mode if needed);
  - `lakehouse_maintenance` (daily).
- **Power BI**: `docs/powerbi.md`.
- **Failure testing**: `scripts/failure_tests.py` (9 injections) and `docs/failure_testing.md`
  (matrix with the results so far).
- **Docs**: `README.md` and `docs/architecture.md`.
- **Simulator**: `scripts/simulate_traffic.py`, labelled `sim-` shoppers driving the real API.
- Pipeline spec (in `provision.ps1`): Gold library, `event_log`, `continuous: false`, version
  `1.1.0`.

## Restart runbook (one session, then stop again)

1. **VM**:
   - Run `az vm start -g ekadai-rg -n ekadai-vm`; the containers restart by themselves
     (`unless-stopped`).
   - If your IP changed, update NSG rules `allow-kafka-broker`, `SSH` and `allow-airflow-ui`.
   - Check that the Debezium connector is RUNNING and catches up from its slot.
2. **Airflow**: copy the updated `azure/vm-stack/airflow/` (Dockerfile, compose, `dags/`) to
   `~/vm-stack/airflow/`, run `sudo docker compose up -d --build`, then unpause the DAGs.
3. **Databricks**:
   - create schema `ops`;
   - upload `gold_pipeline.py`;
   - update the pipeline spec (Gold library, `event_log`, version `1.1.0`, triggered);
   - start one update, which catches Bronze up from Kafka and builds Silver + Gold;
   - check 0 warnings;
   - apply `ops_views.sql`.
4. **Traffic**: `python scripts/simulate_traffic.py --sessions 40`, then another triggered
   update. Verify Gold: facts vs Silver counts, the funnel, revenue incl. a cancellation, and
   the as-of keys.
5. **Failure tests**: run the "_run at restart_" rows in `docs/failure_testing.md`, including
   `backfill_reconcile` (run, rerun, failure, corrective run).
6. **Observability**: trigger `kafka_cdc_health` and check the `ops` views.
7. **Power BI**: you connect Power BI Desktop and build the report from `docs/powerbi.md`.
8. **Live demo** (optional, short): set `continuous: true`, show real-time latency, then set
   it back.
9. **Stop everything**: the pipeline (triggered/idle), the warehouse, pause the DAGs, and
   `az vm deallocate`.

## Restart session results (2026-09-29)

**Gold (Phases 11–12): verified.**
- The first update surfaced two issues, both fixed and logged in `bugs_and_fixes.md`:
  - an ambiguous `user_id` in the session query;
  - Gold reading SCD2 through UC views, which hid the dependency from the pipeline graph (the
    dims now read `*_history` directly).
- After that: COMPLETED, 0 warnings.
- 40 simulated sessions ran through the real app (22 browse / 8 cart / 4 abandoned checkout /
  6 orders).
- Checks:
  - 9 orders in CDC = `fact_orders` = `agg_order_metrics`;
  - net sales = Σ line revenue (₹75,774);
  - 409 of 410 events admitted (the excluded one references a `zz-test` product);
  - every order line resolves a product version;
  - the funnel for 2026-09-29 was 43 → 18 → 12 → 8, with 4 abandoned (visible once the 15 min
    passed) and 2 cancelled.

**Observability (Phase 13).**
- `ops` schema created; the pipeline event log is published to `ops.pipeline_event_log`.
- All 13 objects in `ops_views.sql` were created.
- Airflow was rebuilt with `confluent-kafka` and joined to the `vm-stack_default` network. All
  4 DAGs load with no import errors.
- `kafka_cdc_health` ran: 38 partitions and the connector sampled.
- `backfill_reconcile` and `lakehouse_maintenance` haven't been triggered yet.

**Deployment.**
- **API**: `azure/vm-stack/api/` (FastAPI image + Caddy) on the VM.
  - Azure DNS label `ekadai-api` → https://ekadai-api.eastus.cloudapp.azure.com, with a Let's
    Encrypt certificate obtained automatically.
  - NSG `allow-https-api` opens 80/443 to the Internet.
  - Secrets live only in `~/vm-stack/api/api.env` (chmod 600, gitignored): the Supabase pooler
    URL, a new random JWT key, and `CORS_ORIGINS`.
  - Events go to `kafka:9092` inside the VM.
- **Storefront**: Vercel project `ekadai` (team `sidharth131102s-projects`) →
  **https://ekadai-rouge.vercel.app**.
  - `web/vercel.json` rewrites deep links to `index.html`.
  - Deployed with `vercel deploy --prod --build-env VITE_API_BASE_URL=…`.
  - The CORS preflight from that origin was verified.
- **Live latency** (continuous pipeline, public API): event → Silver 58 s on the first run
  after start; → Gold `fact_events` ~92 s.

**Power BI (Phase 14).**
- `powerbi/generate_pbip.py` generates the PBIP from `powerbi/columns.txt`.
- Opened in Desktop; the numbers matched Gold exactly (9 orders, ₹75.77K, AOV ₹8.42K, 22.2%
  cancellation).
- Authenticated with a 7-day Databricks personal access token (the personal Microsoft account
  doesn't work with Entra sign-in).
- The user customised the visuals. Switching that version to DirectQuery needed: only the
  partition modes flipped, plus removing Desktop's 30 auto date tables (they force Import).
  Auto date/time is now off.

**GitHub.** Public repo https://github.com/sidharth131102/ekadai, initial commit `2836ebe` on
`main`.
- Before pushing, the only real secret in the tree was removed: the Supabase password quoted in
  a `bugs_and_fixes.md` error message.
- **Recommended**: change the Supabase database password anyway (it appeared in chat and local
  files), then update `.env` and the VM's `api.env`.

**Still running at the time of writing** (for the screen recording):
- the VM (Kafka, Debezium, Airflow, API, Caddy);
- the pipeline in **continuous** mode;
- the SQL warehouse (DirectQuery).

**Shutdown checklist:**
- pipeline → triggered;
- warehouse stop;
- `az vm deallocate` (takes the public API offline; the Vercel storefront stays up but can't
  load data);
- revoke the Power BI and Airflow Databricks tokens.

**Open items:**
- trigger `backfill_reconcile` (run / rerun / failure / corrective) and `lakehouse_maintenance`;
- the broker-outage and Debezium-restart failure tests;
- Gold late-replay admission;
- product images for the remaining categories;
- rotate the Supabase password.
