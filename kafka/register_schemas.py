"""Idempotently registers all 18 event schemas into the Schema Registry, one subject per event
type, using TopicRecordNameStrategy (§41): subject = "{topic}-{namespace}.{record_name}". Reads
the raw `.avsc` files directly — the actual contract artifacts (`schema_builder.py`'s own
docstring) — rather than re-deriving a schema representation from the fastavro-parsed form.

`register_schema` is idempotent by design: registering byte-identical content against an
existing subject returns the existing schema ID rather than creating a new version, so this is
safe to re-run.

Run as `python -m kafka.register_schemas` against a running local Schema Registry
(`kafka/docker-compose.yml`).
"""

from __future__ import annotations

import json
import sys

from confluent_kafka.schema_registry import Schema, SchemaRegistryClient

from app.config import settings
from events.registry import EVENT_TYPES, SCHEMAS_DIR


def subject_for(event_type: str) -> str:
    info = EVENT_TYPES[event_type]
    raw = json.loads((SCHEMAS_DIR / f"{event_type}.avsc").read_text(encoding="utf-8"))
    return f"{info.topic}-{raw['namespace']}.{raw['name']}"


def main() -> None:
    client = SchemaRegistryClient({"url": settings.schema_registry_url})

    for event_type in EVENT_TYPES:
        subject = subject_for(event_type)
        raw_text = (SCHEMAS_DIR / f"{event_type}.avsc").read_text(encoding="utf-8")
        schema = Schema(raw_text, schema_type="AVRO")
        try:
            schema_id = client.register_schema(subject, schema)
        except Exception as exc:  # noqa: BLE001 — surface registry errors verbatim
            print(f"FAILED {event_type} -> {subject}: {exc}")
            sys.exit(1)
        print(f"{event_type:25s} -> {subject:70s} id={schema_id}")

    print(f"Done. {len(EVENT_TYPES)} subjects registered/verified.")


if __name__ == "__main__":
    main()
