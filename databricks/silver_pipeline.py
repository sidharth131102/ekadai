"""Phase 7 — Silver behavioral events, validated and deduplicated, in the same continuous
pipeline as Bronze (one always-on compute, real-time end to end).

Reads `bronze_events` as a stream, validates every event with `silver_rules.validate_event`
(pure Python, unit-tested locally), and splits the result three ways, all published into
`ekadai_databricks.silver`:

- `silver_events` (§54) — valid events only, exactly the spec's column list. Written with AUTO
  CDC keyed on `event_id` (SCD type 1): true upsert semantics, so a duplicate event_id never
  produces a second row (§56, §57), and later phases can update a row in place by event_id
  (reference resolution, §61).
- `silver_event_filters` (§68) — one row per filter of each valid `filter_applied` event, keyed
  on (`event_id`, `filter_index`). `filter_index` isn't in §68's field list; it's the filter's
  position within the event, needed to make "one row per filter" an idempotent key.
- `silver_event_quarantine` (§64) — every invalid or undecodable event, keyed on its Kafka
  coordinates (a malformed message may have no event_id). For undecodable messages
  `raw_payload` holds the base64 of the original bytes, so the quarantine row is self-contained.

- `reference_resolution_queue` (§62) — Phase 9; see "Reference resolution" below.

Late data (Phase 10, §65–67): `is_late` / `is_too_late` compare Kafka append time with event
time against the configured watermark (10 min) and allowed lateness (5 min). Too-late events
stay in Silver; the Airflow `late_data_replay` DAG queues and replays them
(`late_data_replay_queue`), and Gold only admits them once replayed.

Reference resolution (Phase 9, §60–63): every valid event's user / product / category ids are
checked against what CDC has delivered, giving `reference_status` RESOLVED / PARTIALLY_RESOLVED /
UNRESOLVED and `reference_errors` (e.g. `UNKNOWN_PRODUCT:<id>`). When a missing reference
arrives later, the affected events are corrected in place by `event_id` — streaming, no job.
Race-free by construction — silver_events' AUTO CDC source is a union of (a) new valid events
and (b) corrections: when a reference first appears in CDC, every event referencing it is
re-derived from `bronze_events` (read statically) and re-emitted with recomputed status.
  - Existence is looked up in the Bronze CDC tables, re-read every micro-batch. The correction
    triggers stream from those same tables, so anything a batch is triggered by is already
    visible to that batch's lookup.
  - An event already in Bronze when its reference arrives is corrected by (b); one that reaches
    Bronze later is checked by (a) on arrival, when the reference is already in Bronze.
  - Corrections are re-derived from Bronze rather than read back from silver_events because
    the pipeline graph forbids a flow reading its own target (tried; rejected as a cycle).
Corrections are complete rows with a higher `_seq` revision, so AUTO CDC updates the existing
row by event_id — never a partial row, never a second row.
"""

from __future__ import annotations

import sys

import dlt
from pyspark.sql.functions import (
    array,
    coalesce,
    col,
    concat,
    count_distinct,
    current_timestamp,
    expr,
    filter as array_filter,
    first,
    get_json_object,
    greatest,
    lit,
    max as max_,
    min as min_,
    posexplode,
    size,
    struct,
    sum as sum_,
    timestamp_millis,
    udf,
    unix_millis,
    when,
)
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

sys.path.append("/Workspace/ekadai")
import silver_rules  # noqa: E402  (workspace file, uploaded next to this source)

# Ship the rules module to workers by value — module-level references pickle by name and don't
# exist on workers (the Phase 6 UDF failure).
from pyspark import cloudpickle as _cloudpickle  # noqa: E402

_cloudpickle.register_pickle_by_value(silver_rules)

CATALOG = "ekadai_databricks"
SILVER = f"{CATALOG}.silver"
SILVER_EVENTS = f"{SILVER}.silver_events"

# Reference types (§62): (type, event column, Bronze CDC entity, trigger topic code)
REFERENCES = [
    ("USER", "user_id", "users", 1),
    ("PRODUCT", "product_id", "products", 2),
    ("CATEGORY", "category_id", "categories", 3),
]
RESOLVED, PARTIALLY_RESOLVED, UNRESOLVED = "RESOLVED", "PARTIALLY_RESOLVED", "UNRESOLVED"
PENDING_FAIL_AFTER = "7 days"  # Kafka retention — a reference that hasn't arrived by then won't
PIPELINE_VERSION = spark.conf.get("ekadai.pipeline_version", "unversioned")  # noqa: F821 — pipeline runtime
# §65 initial values; pipeline config so they can be tuned after empirical validation.
WATERMARK_MS = int(spark.conf.get("ekadai.watermark_minutes", "10")) * 60_000  # noqa: F821
ALLOWED_LATENESS_MS = int(spark.conf.get("ekadai.allowed_lateness_minutes", "5")) * 60_000  # noqa: F821

_STRING_FIELDS = [
    "event_id", "event_type", "user_id", "session_id", "product_id", "category_id", "cart_id",
    "checkout_id", "order_id", "device_type", "operating_system", "browser", "search_query",
    "gross_merchandise_value", "discount_amount", "cart_net_value", "order_value", "currency",
    "source", "source_system",
]
_INT_FIELDS = [
    "schema_version", "search_result_count", "quantity_added", "quantity_removed",
    "cart_quantity_after", "item_count", "total_quantity",
]
_FILTER_TYPE = StructType([
    StructField("filter_type", StringType()),
    StructField("filter_value_string", StringType()),
    StructField("filter_value_min", DoubleType()),
    StructField("filter_value_max", DoubleType()),
    StructField("filter_value_boolean", BooleanType()),
    StructField("category_id", StringType()),
])
CHECK_TYPE = StructType(
    [StructField("error_type", StringType()), StructField("validation_error", StringType())]
    + [StructField(n, StringType()) for n in _STRING_FIELDS]
    + [StructField(n, IntegerType()) for n in _INT_FIELDS]
    + [StructField("event_timestamp_ms", LongType()), StructField("filters", ArrayType(_FILTER_TYPE))]
)


def _make_checker():
    string_fields, int_fields = list(_STRING_FIELDS), list(_INT_FIELDS)

    def check(raw_payload, decode_error, kafka_topic):
        # Never raises — coerces every field to its declared type, so an odd value can only
        # ever land in quarantine, never crash the stream.
        import json

        try:
            envelope = json.loads(raw_payload) if raw_payload is not None else None
        except ValueError as exc:
            envelope, decode_error = None, decode_error or f"raw_payload is not JSON: {exc}"
        try:
            result = silver_rules.validate_event(envelope, decode_error, kafka_topic)
        except Exception as exc:  # noqa: BLE001
            result = {"error_type": silver_rules.MALFORMED, "errors": [f"validator crashed: {exc!r}"], "fields": {}}

        fields = result["fields"]
        out = {
            "error_type": result["error_type"],
            "validation_error": "; ".join(result["errors"])[:4000] or None,
        }
        for name in string_fields:
            v = fields.get(name)
            out[name] = None if v is None else str(v)
        for name in int_fields:
            v = fields.get(name)
            out[name] = v if isinstance(v, int) and not isinstance(v, bool) and abs(v) < 2**31 else None
        ts = fields.get("event_timestamp_ms")
        out["event_timestamp_ms"] = ts if isinstance(ts, int) and not isinstance(ts, bool) else None

        filters = fields.get("filters")
        if result["error_type"] is None and isinstance(filters, list):
            out["filters"] = [
                {
                    "filter_type": f.get("filter_type"),
                    "filter_value_string": f.get("filter_value_string"),
                    "filter_value_min": None if f.get("filter_value_min") is None else float(f["filter_value_min"]),
                    "filter_value_max": None if f.get("filter_value_max") is None else float(f["filter_value_max"]),
                    "filter_value_boolean": f.get("filter_value_boolean"),
                    "category_id": f.get("category_id"),
                }
                for f in filters
            ]
        else:
            out["filters"] = None
        return out

    return check


check_udf = udf(_make_checker(), CHECK_TYPE)


def _auto_cdc(target: str, source: str, keys: list[str], sequence_by: str) -> None:
    create = getattr(dlt, "create_auto_cdc_flow", None) or dlt.apply_changes
    create(
        target=target,
        source=source,
        keys=keys,
        sequence_by=col(sequence_by),
        stored_as_scd_type=1,
        except_column_list=[sequence_by],
    )


@dlt.view(comment="Every Bronze behavioral event with its validation verdict and extracted §54 fields.")
def silver_event_checks():
    return (
        dlt.read_stream("bronze_events")
        .withColumn("chk", check_udf(col("raw_payload"), col("decode_error"), col("kafka_topic")))
        .withColumn("_seq", struct(col("kafka_timestamp"), col("kafka_partition"), col("kafka_offset")))
    )


# --- silver_events (§54) -------------------------------------------------------------------

# §54 column order. reference_status / reference_errors are computed by _with_reference_status.
EVENT_COLUMNS = [
    "event_id", "event_type", "schema_version", "user_id", "session_id", "product_id", "category_id",
    "cart_id", "checkout_id", "order_id", "event_timestamp", "ingestion_timestamp", "processing_timestamp",
    "device_type", "operating_system", "browser", "search_query", "search_result_count", "quantity_added",
    "quantity_removed", "cart_quantity_after", "item_count", "total_quantity", "gross_merchandise_value",
    "discount_amount", "cart_net_value", "order_value", "currency", "source", "kafka_topic", "kafka_partition",
    "kafka_offset", "kafka_timestamp", "source_system", "pipeline_version", "validation_status",
    "reference_status", "reference_errors", "is_late", "is_too_late",
]


def _seq(revision, trigger_topic, trigger_offset):
    # Originals: revision 0. Corrections: the correction time plus the trigger's Kafka coordinates,
    # so a correction always outranks the original and two corrections in one batch never tie.
    return struct(
        col("kafka_timestamp").alias("kafka_timestamp"),
        col("kafka_partition").alias("kafka_partition"),
        col("kafka_offset").alias("kafka_offset"),
        revision.cast("long").alias("revision"),
        trigger_topic.cast("int").alias("trigger_topic"),
        trigger_offset.cast("long").alias("trigger_offset"),
    )


def _known_ids(entity: str, id_col: str):
    # Static read — re-evaluated at every micro-batch, so it always includes whatever the trigger
    # streams (which read these same tables) are delivering in that batch. A later DELETE doesn't
    # un-resolve: the reference did exist (§50).
    return (
        dlt.read(f"bronze_cdc_{entity}")
        .where(col("decode_error").isNull() & col("op").isin("c", "r", "u"))
        .select(get_json_object(col("after_json"), f"$.{id_col}").alias("_known_id"))
        .where(col("_known_id").isNotNull())
        .distinct()
    )


def _with_reference_status(df):
    """§60/§63: each reference checked independently; an unknown product never implies an
    unknown category."""
    misses = []
    n_refs = lit(0)
    n_miss = lit(0)
    for ref_type, id_col, entity, _ in REFERENCES:
        known = _known_ids(entity, id_col).withColumnRenamed("_known_id", f"_known_{id_col}")
        df = df.join(known, df[id_col] == known[f"_known_{id_col}"], "left")
        miss = col(id_col).isNotNull() & col(f"_known_{id_col}").isNull()
        misses.append(when(miss, concat(lit(f"UNKNOWN_{ref_type}:"), col(id_col))))
        n_refs = n_refs + when(col(id_col).isNotNull(), 1).otherwise(0)
        n_miss = n_miss + when(miss, 1).otherwise(0)
    errors = array_filter(array(*misses), lambda e: e.isNotNull())
    return (
        df.withColumn("reference_status",
                      when(n_miss == 0, lit(RESOLVED)).when(n_miss == n_refs, lit(UNRESOLVED)).otherwise(lit(PARTIALLY_RESOLVED)))
        .withColumn("reference_errors", when(size(errors) > 0, errors))
        .select(*EVENT_COLUMNS, "_seq")
    )


def _project(checked, seq):
    """Bronze rows + `chk` verdict -> the §54 columns (minus reference status) + `_seq`. Shared
    by new events and corrections, so a corrected row is derived exactly like the original."""
    money = "decimal(18,2)"
    return checked.where(col("chk.error_type").isNull()).select(
        col("chk.event_id").alias("event_id"),
        col("chk.event_type").alias("event_type"),
        col("chk.schema_version").alias("schema_version"),
        col("chk.user_id").alias("user_id"),
        col("chk.session_id").alias("session_id"),
        col("chk.product_id").alias("product_id"),
        col("chk.category_id").alias("category_id"),
        col("chk.cart_id").alias("cart_id"),
        col("chk.checkout_id").alias("checkout_id"),
        col("chk.order_id").alias("order_id"),
        timestamp_millis(col("chk.event_timestamp_ms")).alias("event_timestamp"),
        col("ingestion_timestamp"),
        current_timestamp().alias("processing_timestamp"),
        col("chk.device_type").alias("device_type"),
        col("chk.operating_system").alias("operating_system"),
        col("chk.browser").alias("browser"),
        col("chk.search_query").alias("search_query"),
        col("chk.search_result_count").alias("search_result_count"),
        col("chk.quantity_added").alias("quantity_added"),
        col("chk.quantity_removed").alias("quantity_removed"),
        col("chk.cart_quantity_after").alias("cart_quantity_after"),
        col("chk.item_count").alias("item_count"),
        col("chk.total_quantity").alias("total_quantity"),
        col("chk.gross_merchandise_value").cast(money).alias("gross_merchandise_value"),
        col("chk.discount_amount").cast(money).alias("discount_amount"),
        col("chk.cart_net_value").cast(money).alias("cart_net_value"),
        col("chk.order_value").cast(money).alias("order_value"),
        col("chk.currency").alias("currency"),
        col("chk.source").alias("source"),
        col("kafka_topic"),
        col("kafka_partition"),
        col("kafka_offset"),
        col("kafka_timestamp"),
        col("chk.source_system").alias("source_system"),
        lit(PIPELINE_VERSION).alias("pipeline_version"),
        lit("VALID").alias("validation_status"),
        # §65/§66 lateness = Kafka append time − event time. Kafka's timestamp, not Bronze's
        # ingestion_timestamp: it doesn't change when Bronze is replayed, so a full refresh can't
        # make old events look late. Too-late events stay here; Gold holds them back until the
        # Airflow replay DAG processes them.
        ((unix_millis(col("kafka_timestamp")) - col("chk.event_timestamp_ms")) > WATERMARK_MS).alias("is_late"),
        ((unix_millis(col("kafka_timestamp")) - col("chk.event_timestamp_ms")) > WATERMARK_MS + ALLOWED_LATENESS_MS)
        .alias("is_too_late"),
        seq.alias("_seq"),
    )


def _new_valid_events():
    return _project(dlt.read_stream("silver_event_checks"), _seq(lit(0), lit(0), lit(0)))


# Where each reference id sits in a Bronze behavioral envelope.
_REF_JSON_PATH = {"user_id": "$.context.user_id", "product_id": "$.payload.product_id", "category_id": "$.payload.category_id"}


def _corrections():
    """When a reference first appears in CDC (insert or snapshot), re-derive every event that
    references it from Bronze and re-emit it with recomputed status.

    The events are re-derived from `bronze_events` (read statically, so every event already in
    Bronze is seen), not read back from silver_events — the pipeline graph forbids a flow
    reading its own target. Race-free: an event already in Bronze when the reference arrives is
    corrected here; one that reaches Bronze later is checked on its own arrival, by which time
    the reference is in Bronze. Later UPDATEs of a reference don't trigger anything — it already
    existed."""
    out = None
    for ref_type, id_col, entity, topic_code in REFERENCES:
        triggers = (
            dlt.read_stream(f"bronze_cdc_{entity}")
            .where(col("decode_error").isNull() & col("op").isin("c", "r"))
            .select(
                get_json_object(col("after_json"), f"$.{id_col}").alias("_trigger_id"),
                col("kafka_partition").alias("_trigger_partition"),
                col("kafka_offset").alias("_trigger_offset"),
            )
        )
        referencing = (
            dlt.read("bronze_events")
            .where(col("decode_error").isNull())
            .withColumn("_ref_id", get_json_object(col("raw_payload"), _REF_JSON_PATH[id_col]))
        )
        matched = (
            triggers.join(referencing, triggers["_trigger_id"] == referencing["_ref_id"], "inner")
            .withColumn("chk", check_udf(col("raw_payload"), col("decode_error"), col("kafka_topic")))
        )
        fixed = _project(
            matched,
            _seq(unix_millis(current_timestamp()), lit(topic_code * 1000) + col("_trigger_partition"), col("_trigger_offset")),
        )
        out = fixed if out is None else out.unionByName(fixed)
    return out


@dlt.view(comment="New valid events plus reference-arrival corrections, with reference status (§54, §60–63).")
def silver_events_valid():
    base = [c for c in EVENT_COLUMNS if c not in ("reference_status", "reference_errors")]
    events = _new_valid_events().select(*base, "_seq")
    fixes = _corrections().select(*base, "_seq")
    return _with_reference_status(events.unionByName(fixes))


dlt.create_streaming_table(
    name=f"{SILVER}.silver_events",
    comment="Validated, deduplicated behavioral events (§54). One row per event_id.",
)
_auto_cdc(f"{SILVER}.silver_events", "silver_events_valid", ["event_id"], "_seq")


# --- reference_resolution_queue (§62) --------------------------------------------------------

@dlt.table(
    name=f"{SILVER}.reference_resolution_queue",
    comment="One row per reference some event needed before CDC delivered it (§62). Derived, so it can't drift.",
)
def reference_resolution_queue():
    events = spark.read.table(SILVER_EVENTS)  # noqa: F821
    needed = None
    for ref_type, id_col, entity, _ in REFERENCES:
        arrivals = (
            dlt.read(f"bronze_cdc_{entity}")
            .where(col("decode_error").isNull() & col("op").isin("c", "r", "u"))
            .groupBy(get_json_object(col("after_json"), f"$.{id_col}").alias("reference_id"))
            .agg(min_("ingestion_timestamp").alias("arrived_at"))
        )
        refs = events.where(col(id_col).isNotNull()).select(
            lit(ref_type).alias("reference_type"),
            col(id_col).alias("reference_id"),
            "event_id",
            "ingestion_timestamp",
            # Is this event still waiting on this particular reference?
            expr(f"array_contains(coalesce(reference_errors, array()), concat('UNKNOWN_{ref_type}:', {id_col}))")
            .alias("still_unresolved"),
        )
        # An event "needed" the reference if it landed before the reference did (or it never did).
        part = refs.join(arrivals, "reference_id", "left").where(
            col("arrived_at").isNull() | (col("ingestion_timestamp") < col("arrived_at"))
        )
        needed = part if needed is None else needed.unionByName(part)

    q = needed.groupBy("reference_type", "reference_id").agg(
        min_("ingestion_timestamp").alias("first_seen_at"),
        max_("ingestion_timestamp").alias("last_seen_at"),
        count_distinct("event_id").alias("affected_event_count"),
        first("arrived_at", ignorenulls=True).alias("resolved_at"),
        sum_(when(col("still_unresolved"), 1).otherwise(0)).alias("_still_unresolved"),
    )
    too_old = col("first_seen_at") < current_timestamp() - expr(f"INTERVAL {PENDING_FAIL_AFTER}")
    status = (
        when(col("resolved_at").isNull() & too_old, lit("FAILED"))
        .when(col("resolved_at").isNull(), lit("PENDING"))
        .when(col("_still_unresolved") > 0, lit("PROCESSING"))
        .otherwise(lit("RESOLVED"))
    )
    return q.select(
        expr("xxhash64(reference_type, reference_id)").alias("resolution_id"),
        "reference_type",
        "reference_id",
        "first_seen_at",
        "last_seen_at",
        status.alias("status"),
        # Each later event that re-checked the id and still missed is a retry in this
        # event-driven design (there's no polling loop to count).
        (col("affected_event_count") - 1).alias("retry_count"),
        greatest(col("last_seen_at"), col("resolved_at")).alias("last_attempt_at"),
        "resolved_at",
        when(col("resolved_at").isNull() & too_old,
             concat(lit("no CDC record for this "), col("reference_type"), lit(f" after {PENDING_FAIL_AFTER}")))
        .alias("error_message"),
        "affected_event_count",
    )


# --- silver_event_filters (§68) ------------------------------------------------------------

@dlt.view
def silver_event_filters_source():
    return (
        dlt.read_stream("silver_event_checks")
        .where(col("chk.error_type").isNull() & (col("chk.event_type") == "filter_applied"))
        .select(col("chk.event_id").alias("event_id"), col("_seq"), posexplode(col("chk.filters")).alias("filter_index", "f"))
        .select(
            "event_id",
            "filter_index",
            col("f.filter_type").alias("filter_type"),
            col("f.filter_value_string").alias("filter_value_string"),
            col("f.filter_value_min").alias("filter_value_min"),
            col("f.filter_value_max").alias("filter_value_max"),
            col("f.filter_value_boolean").alias("filter_value_boolean"),
            col("f.category_id").alias("category_id"),
            "_seq",
        )
    )


dlt.create_streaming_table(
    name=f"{SILVER}.silver_event_filters",
    comment="One row per filter within one filter_applied event (§68).",
)
_auto_cdc(f"{SILVER}.silver_event_filters", "silver_event_filters_source", ["event_id", "filter_index"], "_seq")


# --- silver_event_quarantine (§64) ---------------------------------------------------------

@dlt.view
def silver_event_quarantine_source():
    return dlt.read_stream("silver_event_checks").where(col("chk.error_type").isNotNull()).select(
        col("chk.event_id").alias("event_id"),
        col("chk.event_type").alias("event_type"),
        col("chk.schema_version").alias("schema_version"),
        coalesce(col("raw_payload"), expr("concat('base64:', base64(raw_value))")).alias("raw_payload"),
        col("chk.error_type").alias("error_type"),
        col("chk.validation_error").alias("validation_error"),
        col("kafka_topic"),
        col("kafka_partition"),
        col("kafka_offset"),
        col("kafka_timestamp"),
        col("ingestion_timestamp"),
        current_timestamp().alias("detected_at"),
        col("chk.source_system").alias("source_system"),
        lit(PIPELINE_VERSION).alias("pipeline_version"),
        col("_seq"),
    )


dlt.create_streaming_table(
    name=f"{SILVER}.silver_event_quarantine",
    comment="Invalid or undecodable behavioral events (§64). Bronze always keeps the original.",
)
_auto_cdc(
    f"{SILVER}.silver_event_quarantine",
    "silver_event_quarantine_source",
    ["kafka_topic", "kafka_partition", "kafka_offset"],
    "_seq",
)
