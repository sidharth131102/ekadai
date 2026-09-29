"""Phases 11–12 — Gold dimensions, facts and aggregates (§74–91), as materialized views in the
same pipeline, published to `ekadai_databricks.gold`.

Why materialized views: every Gold grain here is a pure function of Silver, so an MV is always
exactly "Silver's current state, reshaped" — corrections upstream (reference resolution §61,
late replay §66, CDC status changes) flow into Gold on the next refresh with no bespoke
correction logic, and re-running is idempotent by construction (§57).

Conventions:
- Surrogate keys (§76) are deterministic hashes: SCD2 dims reuse the Silver `*_version_key`
  (xxhash64 of id + WAL position), facts use xxhash64 of the business id, `dim_date` uses
  YYYYMMDD. Same keys after any rebuild.
- "As of" joins: a fact row points at the dimension version valid at its event/order time
  (§78 "historical facts point to the historical version"). If the fact predates the first
  version (e.g. `user_registered` fires a moment before the user row commits), the earliest
  version is used. A reference that never resolved yields a null key (unknown member).
- Admission (§66): an event reaches Gold if it isn't `is_too_late`, or its
  `late_data_replay_queue` record is PROCESSED (the Airflow replay DAG's output).
- Synthetic test products (brand `zz-test`, used to test SCD2 ordering and reference
  resolution) are excluded from Gold.
- All dates are UTC (§58). Sessions: 30 min inactivity within a session_id (§83).
"""

from __future__ import annotations

import dlt

CATALOG = "ekadai_databricks"
S = f"{CATALOG}.silver"
G = f"{CATALOG}.gold"


def sql(text: str):
    return spark.sql(text)  # noqa: F821 — pipeline runtime


def date_key(ts: str) -> str:
    return f"CAST(date_format({ts}, 'yyyyMMdd') AS INT)"


DEVICE_KEY = "xxhash64(coalesce(device_type, '~'), coalesce(operating_system, '~'), coalesce(browser, '~'))"


def as_of(src: str, part: str, left_id: str, ts: str, dim: str, dim_id: str, picks: str) -> str:
    """Attach the dimension version valid at `ts` (else the earliest one) to each row of src."""
    return f"""
    SELECT s.*, {picks}
    FROM ({src}) s
    LEFT JOIN {dim} d ON d.{dim_id} = s.{left_id}
    QUALIFY row_number() OVER (
      PARTITION BY s.{part}
      ORDER BY CASE WHEN d.valid_from <= s.{ts} AND (d.valid_to IS NULL OR s.{ts} < d.valid_to) THEN 0 ELSE 1 END,
               d.valid_from
    ) = 1"""


def scd2(entity: str, key: str) -> str:
    """The spec-shaped SCD2 rows (same mapping as databricks/silver_views.sql), read straight from
    the pipeline's *_history table. Reading the UC views instead hides the dependency from the
    pipeline graph, so it couldn't order the history refresh before Gold."""
    return f"""
    SELECT *,
           xxhash64({key}, __START_AT.change_position) AS version_key,
           CASE WHEN __START_AT.snapshot THEN least(created_at, __START_AT.change_timestamp)
                ELSE __START_AT.change_timestamp END AS valid_from,
           __END_AT.change_timestamp AS valid_to,
           __END_AT IS NULL AS is_current
    FROM {S}.silver_{entity}_history"""


TEST_PRODUCTS = f"SELECT product_id FROM {S}.silver_products_history WHERE brand = 'zz-test'"

# Events admitted to Gold (§66) — too-late ones only once replayed; no synthetic test products.
ADMITTED = f"""
SELECT e.*
FROM {S}.silver_events e
WHERE (NOT coalesce(e.is_too_late, false)
       OR e.event_id IN (SELECT record_id FROM {S}.late_data_replay_queue WHERE status = 'PROCESSED'))
  AND (e.product_id IS NULL OR e.product_id NOT IN ({TEST_PRODUCTS}))
"""

# §83 sessionization: a new session starts on a session_id's first event or after a 30-minute gap.
SESSIONIZED = f"""
SELECT *, xxhash64(session_id, session_seq) AS session_key
FROM (
  SELECT *, sum(new_session) OVER (PARTITION BY session_id ORDER BY event_timestamp, event_id
                                   ROWS UNBOUNDED PRECEDING) AS session_seq
  FROM (
    SELECT a.*,
           CASE WHEN lag(event_timestamp) OVER w IS NULL
                  OR event_timestamp > lag(event_timestamp) OVER w + INTERVAL 30 MINUTES
                THEN 1 ELSE 0 END AS new_session
    FROM ({ADMITTED}) a
    WHERE session_id IS NOT NULL
    WINDOW w AS (PARTITION BY session_id ORDER BY event_timestamp, event_id)
  )
)
"""

# Current state of each order / order item from the CDC change logs (§84: one row per order,
# current status authoritative). A physical DELETE keeps the last known image (§50).
ORDERS_NOW = f"""
SELECT * FROM {S}.silver_cdc_orders WHERE operation <> 'DELETE'
QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY change_position DESC) = 1
"""
ITEMS_NOW = f"""
SELECT * FROM {S}.silver_cdc_order_items WHERE operation <> 'DELETE'
QUALIFY row_number() OVER (PARTITION BY order_item_id ORDER BY change_position DESC) = 1
"""


# --- dimensions (§76–81) -----------------------------------------------------------------------

@dlt.table(name=f"{G}.dim_date", comment="Calendar dimension, ISO weeks (§80). date_key = YYYYMMDD.")
def dim_date():
    return sql(f"""
    SELECT {date_key('d')} AS date_key, d AS date, day(d) AS day, date_format(d, 'EEEE') AS day_name,
           weekofyear(d) AS week_of_year, month(d) AS month, date_format(d, 'MMMM') AS month_name,
           quarter(d) AS quarter, year(d) AS year, dayofweek(d) IN (1, 7) AS is_weekend
    FROM (SELECT explode(sequence(DATE'2026-01-01', DATE'2027-12-31', INTERVAL 1 DAY)) AS d)
    """)


@dlt.table(name=f"{G}.dim_device", comment="Distinct device/OS/browser combinations (§81). No device id, no SCD2.")
def dim_device():
    return sql(f"""
    SELECT {DEVICE_KEY} AS device_key, device_type, operating_system, browser
    FROM (SELECT DISTINCT device_type, operating_system, browser FROM {S}.silver_events)
    """)


@dlt.table(name=f"{G}.dim_category", comment="Category versions, SCD2 (§79).")
def dim_category():
    return sql(f"""
    SELECT version_key AS category_key, category_id, category_name, category_status,
           valid_from, valid_to, is_current
    FROM ({scd2('categories', 'category_id')})
    """)


@dlt.table(name=f"{G}.dim_user", comment="User versions, SCD2 (§77). No email/phone/password/address/last_login.")
def dim_user():
    return sql(f"""
    SELECT version_key AS user_key, user_id, registration_date, account_status, city, state,
           valid_from, valid_to, is_current
    FROM ({scd2('users', 'user_id')})
    """)


@dlt.table(name=f"{G}.dim_product", comment="Product versions, SCD2 (§78); category_key = category version valid when the product version began.")
def dim_product():
    src = f"SELECT * FROM ({scd2('products', 'product_id')}) WHERE coalesce(brand, '') <> 'zz-test'"
    return sql(f"""
    SELECT version_key AS product_key, product_id, product_name, category_key, brand, base_price,
           product_status, valid_from, valid_to, is_current
    FROM ({as_of(src, 'version_key', 'category_id', 'valid_from', f'({scd2("categories", "category_id")})', 'category_id',
                 'd.version_key AS category_key')})
    """)


# --- facts (§82–85) ----------------------------------------------------------------------------

@dlt.table(name=f"{G}.fact_events", comment="Behavioral events (§82). No Kafka lineage, diagnostics or money.")
def fact_events():
    with_user = as_of(ADMITTED, "event_id", "user_id", "event_timestamp", f"{G}.dim_user", "user_id", "d.user_key")
    with_product = as_of(with_user, "event_id", "product_id", "event_timestamp", f"{G}.dim_product", "product_id",
                         "d.product_key, d.category_key AS product_category_key")
    with_category = as_of(with_product, "event_id", "category_id", "event_timestamp", f"{G}.dim_category",
                          "category_id", "d.category_key AS event_category_key")
    return sql(f"""
    SELECT xxhash64(event_id) AS event_key, event_id, event_type, schema_version,
           user_key, session_id, product_key,
           coalesce(event_category_key, product_category_key) AS category_key,  -- §63: a product implies its category
           {DEVICE_KEY} AS device_key, {date_key('event_timestamp')} AS date_key,
           event_timestamp, ingestion_timestamp, source
    FROM ({with_category})
    """)


@dlt.table(name=f"{G}.fact_orders", comment="One row per order, current status authoritative (§84). date_key = creation date.")
def fact_orders():
    items = f"SELECT order_id, count(*) AS item_count, sum(quantity) AS total_quantity FROM ({ITEMS_NOW}) GROUP BY order_id"
    with_user = as_of(ORDERS_NOW, "order_id", "user_id", "created_at", f"{G}.dim_user", "user_id", "d.user_key")
    return sql(f"""
    SELECT xxhash64(o.order_id) AS order_key, o.order_id, o.user_key, {date_key('o.created_at')} AS date_key,
           o.status_after AS status,
           o.created_at AS created_timestamp, o.confirmed_at AS confirmed_timestamp, o.cancelled_at AS cancelled_timestamp,
           o.total_amount, o.currency,
           coalesce(i.item_count, 0) AS item_count, coalesce(i.total_quantity, 0) AS total_quantity,
           o.shipping_address_line1, o.shipping_address_line2, o.shipping_city, o.shipping_state,
           o.shipping_postal_code, o.shipping_country
    FROM ({with_user}) o LEFT JOIN ({items}) i ON i.order_id = o.order_id
    """)


@dlt.table(name=f"{G}.fact_order_items", comment="One row per order line (§85). Historical transaction prices only.")
def fact_order_items():
    joined = f"""
    SELECT i.*, o.created_at AS order_created_at, o.user_id
    FROM ({ITEMS_NOW}) i JOIN ({ORDERS_NOW}) o ON o.order_id = i.order_id
    """
    with_user = as_of(joined, "order_item_id", "user_id", "order_created_at", f"{G}.dim_user", "user_id", "d.user_key")
    with_product = as_of(with_user, "order_item_id", "product_id", "order_created_at", f"{G}.dim_product",
                         "product_id", "d.product_key")
    return sql(f"""
    SELECT xxhash64(order_item_id) AS order_item_key, order_item_id, order_id, xxhash64(order_id) AS order_key,
           product_key, user_key, {date_key('order_created_at')} AS date_key,
           quantity, unit_price, discount_amount, line_revenue, currency
    FROM ({with_product})
    """)


# Per-session facts used by fact_sessions and the funnel.
SESSION_FACTS = f"""
SELECT e.session_key, e.session_id,
       max(e.user_id) AS user_id,                   -- anonymous → authenticated stays one session (§83)
       min(e.event_timestamp) AS session_start_timestamp,
       max(e.event_timestamp) AS session_end_timestamp,
       min_by(struct(e.device_type, e.operating_system, e.browser), e.event_timestamp) AS first_device,
       count(*) AS event_count,
       count_if(e.event_type = 'product_view') AS product_view_count,
       count_if(e.event_type = 'search') AS search_count,
       count_if(e.event_type = 'add_to_cart') AS add_to_cart_count,
       count_if(e.event_type = 'remove_from_cart') AS remove_from_cart_count,
       count_if(e.event_type = 'checkout_started') AS checkout_started_count,
       count_if(e.event_type = 'order_created') AS order_created_count,
       min(CASE WHEN e.event_type = 'checkout_started' THEN e.event_timestamp END) AS first_checkout_ts,
       -- Conversion needs the authoritative outcome: the order must exist in the orders CDC (§83).
       min(CASE WHEN e.event_type = 'order_created' AND o.order_id IS NOT NULL THEN e.event_timestamp END) AS first_success_ts,
       max(CASE WHEN e.event_type = 'order_created' AND o.status_after = 'CANCELLED' THEN 1 ELSE 0 END) = 1 AS has_cancelled_order
FROM ({SESSIONIZED}) e
LEFT JOIN ({ORDERS_NOW}) o ON o.order_id = e.order_id
GROUP BY e.session_key, e.session_id
"""


@dlt.table(name=f"{G}.fact_sessions", comment="One row per session: 30 min inactivity ends it (§83). date_key = start date.")
def fact_sessions():
    with_user = as_of(SESSION_FACTS, "session_key", "user_id", "session_start_timestamp", f"{G}.dim_user", "user_id",
                      "d.user_key")
    return sql(f"""
    SELECT session_key, session_id, user_key,
           xxhash64(coalesce(first_device.device_type, '~'), coalesce(first_device.operating_system, '~'),
                    coalesce(first_device.browser, '~')) AS device_key,
           {date_key('session_start_timestamp')} AS date_key,
           session_start_timestamp, session_end_timestamp,
           unix_timestamp(session_end_timestamp) - unix_timestamp(session_start_timestamp) AS session_duration_seconds,
           event_count, product_view_count, search_count, add_to_cart_count, remove_from_cart_count,
           checkout_started_count, order_created_count,
           first_success_ts IS NOT NULL AS converted
    FROM ({with_user})
    """)


# --- aggregates (§86–91) -----------------------------------------------------------------------

@dlt.table(name=f"{G}.agg_user_activity", comment="User × date activity (§86). Anonymous events are not attributed.")
def agg_user_activity():
    return sql(f"""
    SELECT f.date_key, f.user_key,
           count(DISTINCT s.session_key) AS session_count,
           count(*) AS event_count,
           count_if(e.event_type = 'product_view') AS product_view_count,
           count_if(e.event_type = 'search') AS search_count,
           count_if(e.event_type = 'add_to_cart') AS add_to_cart_count,
           count_if(e.event_type = 'remove_from_cart') AS remove_from_cart_count,
           count_if(e.event_type = 'wishlist_added') AS wishlist_added_count,
           count_if(e.event_type = 'wishlist_removed') AS wishlist_removed_count,
           count_if(e.event_type = 'checkout_started') AS checkout_started_count,
           count_if(e.event_type = 'order_created') AS order_created_count,
           count(DISTINCT CASE WHEN e.event_type = 'product_view' THEN e.product_id END) AS unique_products_viewed,
           coalesce(sum(e.quantity_added), 0) AS total_cart_additions,
           coalesce(sum(e.quantity_removed), 0) AS total_cart_removals,
           true AS active_user
    FROM {G}.fact_events f
    JOIN ({ADMITTED}) e ON e.event_id = f.event_id
    LEFT JOIN ({SESSIONIZED}) s ON s.event_id = f.event_id
    WHERE e.user_id IS NOT NULL
    GROUP BY f.date_key, f.user_key
    """)


@dlt.table(name=f"{G}.agg_conversion_funnel", comment="Distinct sessions per funnel stage by session-start date (§87). 15-min abandonment.")
def agg_conversion_funnel():
    return sql(f"""
    SELECT {date_key('session_start_timestamp')} AS date_key,
           count_if(product_view_count > 0) AS product_view_sessions,
           count_if(add_to_cart_count > 0) AS add_to_cart_sessions,
           count_if(checkout_started_count > 0) AS checkout_started_sessions,
           count_if(first_success_ts IS NOT NULL) AS successful_order_sessions,
           -- Abandoned: checkout started, no successful order within 15 min, and 15 min have passed.
           count_if(first_checkout_ts IS NOT NULL
                    AND (first_success_ts IS NULL OR first_success_ts > first_checkout_ts + INTERVAL 15 MINUTES)
                    AND current_timestamp() > first_checkout_ts + INTERVAL 15 MINUTES) AS checkout_abandoned_sessions,
           count_if(has_cancelled_order) AS cancelled_order_sessions
    FROM ({SESSION_FACTS})
    GROUP BY 1
    """)


@dlt.table(name=f"{G}.agg_product_performance", comment="Product × date (§88). GMV = qty × historical unit price; net = GMV − discount.")
def agg_product_performance():
    return sql(f"""
    WITH engagement AS (
      SELECT f.date_key, f.product_key,
             count_if(f.event_type = 'product_view') AS product_view_count,
             count(DISTINCT CASE WHEN f.event_type = 'product_view' THEN e.user_id END) AS unique_viewing_users,
             count_if(f.event_type = 'add_to_cart') AS add_to_cart_count,
             count(DISTINCT CASE WHEN f.event_type = 'add_to_cart' THEN e.user_id END) AS unique_cart_users
      FROM {G}.fact_events f JOIN ({ADMITTED}) e ON e.event_id = f.event_id
      WHERE f.product_key IS NOT NULL
      GROUP BY 1, 2
    ),
    sales AS (
      SELECT date_key, product_key,
             count(DISTINCT order_id) AS order_count,
             sum(quantity) AS units_sold,
             sum(quantity * unit_price) AS gross_merchandise_value,
             sum(discount_amount) AS discount_amount
      FROM {G}.fact_order_items
      WHERE product_key IS NOT NULL
      GROUP BY 1, 2
    )
    SELECT coalesce(e.date_key, s.date_key) AS date_key,
           coalesce(e.product_key, s.product_key) AS product_key,
           p.category_key,
           coalesce(e.product_view_count, 0) AS product_view_count,
           coalesce(e.unique_viewing_users, 0) AS unique_viewing_users,
           coalesce(e.add_to_cart_count, 0) AS add_to_cart_count,
           coalesce(e.unique_cart_users, 0) AS unique_cart_users,
           coalesce(s.order_count, 0) AS order_count,
           coalesce(s.units_sold, 0) AS units_sold,
           coalesce(s.gross_merchandise_value, 0) AS gross_merchandise_value,
           coalesce(s.discount_amount, 0) AS discount_amount,
           coalesce(s.gross_merchandise_value, 0) - coalesce(s.discount_amount, 0) AS net_revenue
    FROM engagement e
    FULL OUTER JOIN sales s ON s.date_key = e.date_key AND s.product_key = e.product_key
    LEFT JOIN {G}.dim_product p ON p.product_key = coalesce(e.product_key, s.product_key)
    """)


@dlt.table(name=f"{G}.agg_daily_revenue", comment="Date × currency (§90). Sales on order date; cancellations on cancellation date.")
def agg_daily_revenue():
    return sql(f"""
    WITH sales AS (
      SELECT i.date_key, i.currency,
             count(DISTINCT i.order_id) AS order_count,
             sum(i.quantity) AS units_sold,
             sum(i.quantity * i.unit_price) AS gross_merchandise_value,
             sum(i.discount_amount) AS discount_amount
      FROM {G}.fact_order_items i
      GROUP BY 1, 2
    ),
    cancels AS (
      SELECT {date_key('o.cancelled_timestamp')} AS date_key, o.currency,
             count(DISTINCT o.order_id) AS cancelled_order_count,
             sum(i.line_revenue) AS cancelled_order_value     -- net transaction value of the cancelled orders
      FROM {G}.fact_orders o JOIN {G}.fact_order_items i ON i.order_id = o.order_id
      WHERE o.status = 'CANCELLED' AND o.cancelled_timestamp IS NOT NULL
      GROUP BY 1, 2
    )
    SELECT coalesce(s.date_key, c.date_key) AS date_key,
           coalesce(s.currency, c.currency) AS currency,
           coalesce(s.order_count, 0) AS order_count,
           coalesce(s.units_sold, 0) AS units_sold,
           coalesce(s.gross_merchandise_value, 0) AS gross_merchandise_value,
           coalesce(s.discount_amount, 0) AS discount_amount,
           coalesce(s.gross_merchandise_value, 0) - coalesce(s.discount_amount, 0) AS net_transaction_sales,
           coalesce(c.cancelled_order_count, 0) AS cancelled_order_count,
           coalesce(c.cancelled_order_value, 0) AS cancelled_order_value,
           coalesce(s.gross_merchandise_value, 0) - coalesce(s.discount_amount, 0)
             - coalesce(c.cancelled_order_value, 0) AS revenue_after_cancellations
    FROM sales s FULL OUTER JOIN cancels c ON c.date_key = s.date_key AND c.currency = s.currency
    """)


@dlt.table(name=f"{G}.agg_order_metrics", comment="Order creation date × currency (§91).")
def agg_order_metrics():
    return sql(f"""
    SELECT date_key, currency,
           count(*) AS order_count,
           count_if(status = 'CONFIRMED') AS confirmed_order_count,
           count_if(status = 'CANCELLED') AS cancelled_order_count,
           sum(total_amount) AS total_order_value,
           CAST(sum(total_amount) / count(*) AS DECIMAL(18,2)) AS average_order_value,
           coalesce(sum(CASE WHEN status = 'CANCELLED' THEN total_amount END), 0) AS cancelled_order_value,
           count_if(status = 'CANCELLED') / count(*) AS cancellation_rate
    FROM {G}.fact_orders
    GROUP BY 1, 2
    """)


@dlt.table(name=f"{G}.agg_product_attribution", comment="7-day view→purchase attribution per product (§89): first qualifying view and purchase per user.")
def agg_product_attribution():
    return sql(f"""
    WITH first_view AS (
      SELECT e.user_id, e.product_id, min(e.event_timestamp) AS view_timestamp
      FROM ({ADMITTED}) e
      WHERE e.event_type = 'product_view' AND e.user_id IS NOT NULL AND e.product_id IS NOT NULL
      GROUP BY 1, 2
    ),
    purchases AS (
      SELECT o.user_id, i.product_id, o.created_at AS purchase_timestamp
      FROM ({ITEMS_NOW}) i JOIN ({ORDERS_NOW}) o ON o.order_id = i.order_id
    ),
    first_purchase AS (
      SELECT v.user_id, v.product_id, v.view_timestamp, min(p.purchase_timestamp) AS purchase_timestamp
      FROM first_view v
      LEFT JOIN purchases p ON p.user_id = v.user_id AND p.product_id = v.product_id
                           AND p.purchase_timestamp >= v.view_timestamp
                           AND p.purchase_timestamp < v.view_timestamp + INTERVAL 7 DAYS
      GROUP BY 1, 2, 3
    )
    SELECT fp.product_id, dp.product_key, dp.product_name,
           count(*) AS viewing_users,
           count(fp.purchase_timestamp) AS converted_users,
           count(fp.purchase_timestamp) / count(*) AS conversion_rate_7d,
           avg(unix_timestamp(fp.purchase_timestamp) - unix_timestamp(fp.view_timestamp)) AS avg_conversion_seconds,
           percentile(unix_timestamp(fp.purchase_timestamp) - unix_timestamp(fp.view_timestamp), 0.5) AS median_conversion_seconds
    FROM first_purchase fp
    LEFT JOIN {G}.dim_product dp ON dp.product_id = fp.product_id AND dp.is_current
    WHERE fp.product_id NOT IN ({TEST_PRODUCTS})
    GROUP BY 1, 2, 3
    """)
