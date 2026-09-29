"""Phase 4 real transport: produces to Kafka using Confluent's standard Avro wire format
(magic byte 0x00 + 4-byte big-endian schema ID + Avro binary body), serialized via the *same*
fastavro-parsed schema `events/registry.py` already loads for validation — no second Avro
library, no chance of the wire format diverging from what `producer.py.validate()` checked.

Schema IDs are resolved once per event type via `SchemaRegistryClient.register_schema`, which is
idempotent (registering byte-identical content against an existing subject returns the existing
ID rather than creating a new version — see `kafka/register_schemas.py`), and cached in memory.

Like every `EventTransport`, `send()` must never raise into the caller's request path — `emit()`
(events/producer.py) already wraps this in try/except, but delivery failures reported
asynchronously by librdkafka (via the produce() callback) are logged here directly, since they
arrive after `send()` has already returned.
"""

from __future__ import annotations

import io
import json
import logging
import struct

from confluent_kafka import Producer
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient
from fastavro import schemaless_writer

from events.registry import EVENT_TYPES, SCHEMAS_DIR

logger = logging.getLogger("events")

MAGIC_BYTE = b"\x00"


def _subject_for(event_type: str) -> str:
    info = EVENT_TYPES[event_type]
    raw = json.loads((SCHEMAS_DIR / f"{event_type}.avsc").read_text(encoding="utf-8"))
    return f"{info.topic}-{raw['namespace']}.{raw['name']}"


class KafkaAvroTransport:
    def __init__(self, bootstrap_servers: str, schema_registry_url: str):
        self._producer = Producer({"bootstrap.servers": bootstrap_servers})
        self._sr_client = SchemaRegistryClient({"url": schema_registry_url})
        self._schema_id_cache: dict[str, int] = {}

    def _schema_id_for(self, event_type: str) -> int:
        cached = self._schema_id_cache.get(event_type)
        if cached is not None:
            return cached
        subject = _subject_for(event_type)
        raw_text = (SCHEMAS_DIR / f"{event_type}.avsc").read_text(encoding="utf-8")
        schema_id = self._sr_client.register_schema(subject, Schema(raw_text, schema_type="AVRO"))
        self._schema_id_cache[event_type] = schema_id
        return schema_id

    def _delivery_callback(self, err, msg) -> None:
        if err is not None:
            logger.error("kafka delivery failed topic=%s error=%s", msg.topic(), err)

    def send(self, topic: str, key: str, event: dict) -> None:
        event_type = event["event_type"]
        schema_id = self._schema_id_for(event_type)
        info = EVENT_TYPES[event_type]

        buffer = io.BytesIO()
        buffer.write(MAGIC_BYTE)
        buffer.write(struct.pack(">I", schema_id))
        schemaless_writer(buffer, info.schema, event)

        self._producer.produce(
            topic,
            key=key.encode("utf-8"),
            value=buffer.getvalue(),
            callback=self._delivery_callback,
        )
        # Serves librdkafka's internal delivery-callback queue without blocking for
        # acknowledgment — matches emit()'s fire-and-forget contract.
        self._producer.poll(0)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)
