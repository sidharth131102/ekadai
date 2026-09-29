"""Phase 6 — Bronze ingestion as a Lakeflow Declarative Pipeline (serverless, continuous mode).

Replaces the two standalone Structured Streaming jobs (`bronze_events.py`, `bronze_cdc.py`),
keeping their data model exactly: same table names under `ekadai_databricks.bronze`, same
columns in the same order, same Kafka topics, same Avro decoding. Only the execution wrapper
changed — why: real-time analytics needs a continuous stream, serverless *jobs* reject infinite
triggers (INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED), classic clusters kept failing to acquire
VMs in this subscription, and serverless *pipelines* support continuous mode without either
problem. Checkpointing, retries and table creation are handled by the pipeline itself.

Tables (§51):
- `bronze_events` — the 5 behavioral topics. `raw_payload` is the full decoded envelope (JSON);
  first-class columns are projections of its outer fields, identical across event types.
- `bronze_cdc_<entity>` for users/products/categories/orders/order_items — full Debezium
  envelope in `raw_payload`, plus before/after/op/ts_ms/source lineage columns.
- Every table also carries `raw_value` (the original Kafka message bytes) and `decode_error`
  (null unless decoding failed). A message that can't be decoded is kept, not dropped and not
  allowed to stop the stream — Silver routes it to quarantine (§42, §51).

Avro decode: behavioral topics use TopicRecordNameStrategy (several schemas per topic), so each
message's schema ID is read from its Confluent wire-format header (magic byte + 4-byte
big-endian ID) and resolved against Schema Registry. CDC topics use the same header, so one UDF
serves both.
"""

from __future__ import annotations

import dlt
from pyspark.sql.functions import col, current_timestamp, get_json_object, udf
from pyspark.sql.types import StringType, StructField, StructType

KAFKA_BOOTSTRAP_SERVERS = "20.102.92.77:29092"
SCHEMA_REGISTRY_URL = "http://20.102.92.77:8081"
BEHAVIORAL_TOPICS = "user-events,product-events,cart-events,checkout-events,order-events"

# entity -> source topic (§45)
CDC_ENTITIES = {
    "users": "cdc-users",
    "products": "cdc-products",
    "categories": "cdc-categories",
    "orders": "cdc-orders",
    "order_items": "cdc-order-items",
}


def _make_envelope_decoder(registry_url: str):
    # Self-contained on purpose: Spark pickles UDFs to ship them to workers, and anything
    # referenced by module-level name (e.g. an lru_cache-wrapped helper, which pickles by
    # reference) fails to resolve there. A closure over a plain dict pickles by value.
    schema_cache: dict[int, dict] = {}

    def to_json_value(value):
        # fastavro turns Avro logical types into Python objects. Write them back as the values
        # that were actually on the wire — timestamp-millis as epoch ms, not a date string,
        # which silently cast to null in event_timestamp before this fix.
        from datetime import datetime

        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        return str(value)  # Decimal, UUID

    def decode(raw: bytes):
        # Never raises: a message that can't be decoded still lands in Bronze with the reason in
        # decode_error (and its bytes in raw_value), and Silver quarantines it. Raising here
        # would stop the whole stream on one bad message (§42, §51).
        import io
        import json
        import struct

        import requests
        from fastavro import schemaless_reader
        from fastavro.schema import parse_schema

        try:
            if raw is None or len(raw) < 5:
                raise ValueError(f"message too short for the Confluent wire format ({0 if raw is None else len(raw)} bytes)")
            if raw[0] != 0:
                raise ValueError(f"unexpected magic byte {raw[0]}")
            schema_id = struct.unpack(">I", raw[1:5])[0]
            schema = schema_cache.get(schema_id)
            if schema is None:
                resp = requests.get(f"{registry_url}/schemas/ids/{schema_id}", timeout=10)
                resp.raise_for_status()
                schema = parse_schema(json.loads(resp.json()["schema"]))
                schema_cache[schema_id] = schema
            record = schemaless_reader(io.BytesIO(raw[5:]), schema)
            return (json.dumps(record, default=to_json_value), None)
        except Exception as exc:  # noqa: BLE001 — every failure mode must become a Bronze row
            return (None, f"{type(exc).__name__}: {exc}"[:1000])

    return decode


decode_envelope_udf = udf(
    _make_envelope_decoder(SCHEMA_REGISTRY_URL),
    StructType([StructField("raw_payload", StringType()), StructField("decode_error", StringType())]),
)


def _read_topics(topics: str):
    return (
        spark.readStream.format("kafka")  # noqa: F821 — `spark` is provided by the pipeline runtime
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", topics)
        .option("startingOffsets", "earliest")
        .load()
        .withColumn("_decoded", decode_envelope_udf(col("value")))
        .withColumn("raw_payload", col("_decoded.raw_payload"))
    )


def _kafka_lineage():
    # raw_value / decode_error are appended last so every pre-existing column keeps its position.
    return [
        col("topic").alias("kafka_topic"),
        col("partition").alias("kafka_partition"),
        col("offset").alias("kafka_offset"),
        col("timestamp").alias("kafka_timestamp"),
        current_timestamp().alias("ingestion_timestamp"),
        col("value").alias("raw_value"),
        col("_decoded.decode_error").alias("decode_error"),
    ]


@dlt.table(name="bronze_events", comment="Raw behavioral events from the 5 behavioral Kafka topics (§51).")
def bronze_events():
    return _read_topics(BEHAVIORAL_TOPICS).select(
        col("raw_payload"),
        get_json_object(col("raw_payload"), "$.event_id").alias("event_id"),
        get_json_object(col("raw_payload"), "$.event_type").alias("event_type"),
        get_json_object(col("raw_payload"), "$.schema_version").cast("int").alias("schema_version"),
        get_json_object(col("raw_payload"), "$.event_timestamp").cast("long").alias("event_timestamp"),
        *_kafka_lineage(),
    )


def _define_cdc_table(entity: str, topic: str) -> None:
    @dlt.table(name=f"bronze_cdc_{entity}", comment=f"Raw Debezium CDC envelopes from {topic} (§45, §46).")
    def _table():
        return _read_topics(topic).select(
            col("raw_payload"),
            get_json_object(col("raw_payload"), "$.before").alias("before_json"),
            get_json_object(col("raw_payload"), "$.after").alias("after_json"),
            get_json_object(col("raw_payload"), "$.op").alias("op"),
            get_json_object(col("raw_payload"), "$.ts_ms").cast("long").alias("ts_ms"),
            get_json_object(col("raw_payload"), "$.source.lsn").cast("long").alias("source_lsn"),
            get_json_object(col("raw_payload"), "$.source.txId").cast("long").alias("source_tx_id"),
            get_json_object(col("raw_payload"), "$.source.snapshot").alias("source_snapshot"),
            *_kafka_lineage(),
        )


for _entity, _topic in CDC_ENTITIES.items():
    _define_cdc_table(_entity, _topic)
