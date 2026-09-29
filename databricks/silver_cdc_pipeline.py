"""Phase 8 — Silver CDC, in the same continuous pipeline as Bronze and Silver events.

Reads the five `bronze_cdc_*` tables as streams and publishes into `ekadai_databricks.silver`:

- `silver_cdc_orders` (§69), `silver_cdc_order_items` (§70) — change logs, one row per CDC
  change, exactly the spec columns. AUTO CDC SCD1 keyed on (entity id, change_position): a
  redelivered message can never add a second row.
- `silver_products_history`, `silver_categories_history`, `silver_users_history` — SCD2
  history kept by AUTO CDC (`stored_as_scd_type=2`). The spec-shaped `silver_products` /
  `silver_categories` / `silver_users` (§71–73) are Unity Catalog views over these
  (`databricks/silver_views.sql`), mapping AUTO CDC's `__START_AT`/`__END_AT` to
  version keys, valid_from/valid_to and is_current.

Ordering (§47, §92): SCD2 is sequenced by the source WAL position (`source.lsn`), never by
arrival order, so an older change that arrives late is slotted into history where it belongs
instead of becoming "current". Duplicates (§47): the same (key, lsn) arriving twice is dropped
before AUTO CDC, so it can't create a second version or change-log row. Deletes (§50): a
DELETE closes the current SCD2 version; history is kept.

Debezium encodings as they appear in Bronze's JSON: timestamps are ISO-8601 strings, DATE is
days since epoch, NUMERIC is a decimal string. Everything is parsed as string first and cast
explicitly, so an unexpected encoding shows up as a null, not a stream failure.

Rows Bronze couldn't decode are skipped here (they stay in Bronze with `decode_error`; §64's
quarantine is for behavioral events). Counting them is Phase 13 observability.
"""

from __future__ import annotations

import dlt
from pyspark.sql.functions import col, expr, from_json, get_json_object, struct, timestamp_millis, when
from pyspark.sql.types import StringType, StructField, StructType

CATALOG = "ekadai_databricks"
SILVER = f"{CATALOG}.silver"
KAFKA_RETENTION = "7 days"  # a redelivered duplicate can't be older than Kafka keeps messages

MONEY = "decimal(18,2)"


def _typed(name: str, kind: str):
    raw = col(f"img.{name}")
    if kind == "ts":
        return raw.cast("timestamp").alias(name)
    if kind == "money":
        return raw.cast(MONEY).alias(name)
    if kind == "int":
        return raw.cast("int").alias(name)
    if kind == "date":  # io.debezium.time.Date — days since 1970-01-01
        return expr(f"date_add(DATE'1970-01-01', CAST(img.{name} AS INT))").alias(name)
    return raw.alias(name)


def _changes(entity: str, keys: list[str], fields: dict[str, str], extra=()):
    """Typed, deduplicated change stream for one CDC table. `fields` maps column -> kind."""
    image = StructType([StructField(n, StringType()) for n in fields])
    before = from_json(col("before_json"), image)
    after = from_json(col("after_json"), image)
    stream = (
        dlt.read_stream(f"bronze_cdc_{entity}")
        .where(col("decode_error").isNull() & col("op").isin("c", "u", "d", "r"))
        .select(
            # A DELETE has no after image — its entity fields come from the before image (§50).
            when(col("op") == "d", before).otherwise(after).alias("img"),
            before.alias("before_img"),
            after.alias("after_img"),
            expr("CASE op WHEN 'c' THEN 'INSERT' WHEN 'u' THEN 'UPDATE' WHEN 'd' THEN 'DELETE' "
                 "ELSE 'SNAPSHOT' END").alias("operation"),
            timestamp_millis(get_json_object(col("raw_payload"), "$.source.ts_ms").cast("long")).alias("change_timestamp"),
            col("source_tx_id").alias("transaction_id"),
            col("source_lsn").alias("change_position"),
            (expr("coalesce(source_snapshot, 'false')") != "false").alias("snapshot"),
            col("kafka_timestamp"),
        )
        .select(
            *[_typed(n, k) for n, k in fields.items()],
            "operation", "change_timestamp", "transaction_id", "change_position", "snapshot",
            *extra,
            "kafka_timestamp",
        )
    )
    not_null = None
    for k in keys + ["change_position"]:
        cond = col(k).isNotNull()
        not_null = cond if not_null is None else not_null & cond
    return (
        stream.where(not_null)
        .withWatermark("kafka_timestamp", KAFKA_RETENTION)
        .dropDuplicatesWithinWatermark(keys + ["change_position"])
        .drop("kafka_timestamp")
    )


def _auto_cdc(target: str, source: str, keys: list[str], sequence_by, scd_type: int, **kwargs) -> None:
    create = getattr(dlt, "create_auto_cdc_flow", None) or dlt.apply_changes
    create(target=target, source=source, keys=keys, sequence_by=sequence_by, stored_as_scd_type=scd_type, **kwargs)


# --- change logs: silver_cdc_orders (§69), silver_cdc_order_items (§70) ------------------------

ORDER_FIELDS = {
    "order_id": "str", "user_id": "str", "total_amount": "money", "currency": "str",
    "created_at": "ts", "confirmed_at": "ts", "cancelled_at": "ts",
    "shipping_address_line1": "str", "shipping_address_line2": "str", "shipping_city": "str",
    "shipping_state": "str", "shipping_postal_code": "str", "shipping_country": "str",
    "status": "str",
}


@dlt.view
def silver_cdc_orders_source():
    return _changes(
        "orders", ["order_id"], ORDER_FIELDS,
        extra=[col("before_img.status").alias("status_before"), col("after_img.status").alias("status_after")],
    ).select(
        "order_id", "operation", "change_timestamp", "transaction_id", "change_position", "snapshot",
        "status_before", "status_after",
        "user_id", "total_amount", "currency", "created_at", "confirmed_at", "cancelled_at",
        "shipping_address_line1", "shipping_address_line2", "shipping_city", "shipping_state",
        "shipping_postal_code", "shipping_country",
    )


dlt.create_streaming_table(name=f"{SILVER}.silver_cdc_orders", comment="One row per CDC change to one orders row (§69).")
_auto_cdc(f"{SILVER}.silver_cdc_orders", "silver_cdc_orders_source", ["order_id", "change_position"],
          col("change_timestamp"), 1)

ORDER_ITEM_FIELDS = {
    "order_item_id": "str", "order_id": "str", "product_id": "str", "quantity": "int",
    "unit_price": "money", "discount_amount": "money", "line_revenue": "money", "currency": "str",
}


@dlt.view
def silver_cdc_order_items_source():
    return _changes("order_items", ["order_item_id"], ORDER_ITEM_FIELDS).select(
        "order_item_id", "order_id", "operation", "change_timestamp", "transaction_id", "change_position",
        "snapshot", "product_id", "quantity", "unit_price", "discount_amount", "line_revenue", "currency",
    )


dlt.create_streaming_table(name=f"{SILVER}.silver_cdc_order_items", comment="One row per CDC change to one order_items row (§70).")
_auto_cdc(f"{SILVER}.silver_cdc_order_items", "silver_cdc_order_items_source", ["order_item_id", "change_position"],
          col("change_timestamp"), 1)


# --- SCD2 reference history: products (§71), categories (§72), users (§73) ---------------------

def _define_scd2(entity: str, key: str, fields: dict[str, str], tracked: list[str]) -> None:
    source_name = f"silver_{entity}_changes"
    target = f"{SILVER}.silver_{entity}_history"

    @dlt.view(name=source_name)
    def _source():
        # _seq orders versions by WAL position (§47); its other fields ride along so the view can
        # read valid_from/valid_to and "opened by the initial snapshot" off __START_AT/__END_AT.
        return _changes(entity, [key], fields).withColumn(
            "_seq", struct(col("change_position"), col("change_timestamp"), col("snapshot"))
        ).select(*fields.keys(), "operation", "_seq")

    dlt.create_streaming_table(
        name=target,
        comment=f"SCD2 history of {entity} kept by AUTO CDC; query the silver_{entity} view instead.",
    )
    _auto_cdc(
        target, source_name, [key], col("_seq"), 2,
        apply_as_deletes=expr("operation = 'DELETE'"),
        except_column_list=["operation", "_seq"],
        # Only real attribute changes open a new version; the rest (updated_at, …) update in place.
        track_history_column_list=tracked,
    )


_define_scd2(
    "products", "product_id",
    {"product_id": "str", "product_name": "str", "category_id": "str", "brand": "str", "base_price": "money",
     "product_status": "str", "created_at": "ts", "updated_at": "ts"},
    ["product_name", "category_id", "brand", "base_price", "product_status"],
)
_define_scd2(
    "categories", "category_id",
    {"category_id": "str", "category_name": "str", "category_status": "str", "created_at": "ts", "updated_at": "ts"},
    ["category_name", "category_status"],
)
# Never selects email / password_hash / phone (§73) — they don't leave Bronze.
_define_scd2(
    "users", "user_id",
    {"user_id": "str", "registration_date": "date", "account_status": "str", "city": "str", "state": "str",
     "created_at": "ts", "updated_at": "ts"},
    ["city", "state", "account_status"],
)
