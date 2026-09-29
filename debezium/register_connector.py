"""Idempotently registers the single PostgreSQL CDC connector covering all 5 tables from §45,
via a PUT to Kafka Connect's REST API (PUT creates-or-updates by name, unlike POST which errors
on an existing name — safe to re-run).

Design notes (see the Phase 5 plan for the full rationale):
- `plugin.name=pgoutput` — native logical replication, no wal2json extension (§44).
- `publication.autocreate.mode=filtered` — Debezium creates the publication itself, scoped to
  exactly `table.include.list`; no manual `CREATE PUBLICATION` needed.
- `snapshot.mode=initial` — snapshot existing rows, then switch to streaming WAL (§49).
- Five chained `RegexRouter` transforms rewrite Debezium's default topic name
  (`{topic.prefix}.public.{table}`) to the pre-existing Phase 4 topic name; a transform that
  doesn't match a given record's topic leaves it unchanged, so chaining all 5 is safe.
- `message.key.columns` overrides `order_items`' outgoing message key from its actual primary
  key (`order_item_id`) to `order_id`, matching §39's partition-key table (preserve per-order
  ordering, not per-line-item ordering) — the other 4 tables' primary keys already match §39
  as-is, so no override needed for them.

Run as `python -m debezium.register_connector` against a running Connect worker
(`CONNECT_URL`, default `http://localhost:8083`). All target-specific values are overridable via
env vars (defaults match the local dev setup) — see the cloud-migration section of
`current_state.md` for the exact values used for the Azure VM + Supabase deployment:
`DB_HOSTNAME=db.<project-ref>.supabase.co`, `DB_NAME=postgres`,
`SCHEMA_REGISTRY_URL_FOR_CONNECTOR=http://schema-registry:8081` (the *container* network name,
since Connect resolves this URL from inside its own container — not `host.docker.internal`,
which was Windows-Docker-Desktop-specific, and not the host-mapped port Kafka's other listener
uses either).
"""

from __future__ import annotations

import json
import os
import sys

import httpx

CONNECT_URL = os.environ.get("CONNECT_URL", "http://localhost:8083")
CONNECTOR_NAME = "ekadai-postgres-cdc"

DB_HOSTNAME = os.environ.get("DB_HOSTNAME", "host.docker.internal")
DB_NAME = os.environ.get("DB_NAME", "ekadai")
# The Schema Registry URL as *Connect's own container* resolves it — not necessarily the same
# host verification scripts on the dev machine use to reach it.
SCHEMA_REGISTRY_URL_FOR_CONNECTOR = os.environ.get(
    "SCHEMA_REGISTRY_URL_FOR_CONNECTOR", "http://host.docker.internal:8081"
)

CONNECTOR_CONFIG = {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": DB_HOSTNAME,
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "debezium",
    "database.dbname": DB_NAME,
    "topic.prefix": "ekadai",
    "plugin.name": "pgoutput",
    "slot.name": "debezium_ekadai",
    "publication.name": "debezium_ekadai_publication",
    "publication.autocreate.mode": "filtered",
    "snapshot.mode": "initial",
    "table.include.list": "public.users,public.products,public.categories,public.orders,public.order_items",
    "message.key.columns": "public.order_items:order_id",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": SCHEMA_REGISTRY_URL_FOR_CONNECTOR,
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": SCHEMA_REGISTRY_URL_FOR_CONNECTOR,
    "transforms": "users,products,categories,orders,order_items",
    "transforms.users.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.users.regex": "(.*)\\.public\\.users",
    "transforms.users.replacement": "cdc-users",
    "transforms.products.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.products.regex": "(.*)\\.public\\.products",
    "transforms.products.replacement": "cdc-products",
    "transforms.categories.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.categories.regex": "(.*)\\.public\\.categories",
    "transforms.categories.replacement": "cdc-categories",
    "transforms.orders.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.orders.regex": "(.*)\\.public\\.orders",
    "transforms.orders.replacement": "cdc-orders",
    "transforms.order_items.type": "org.apache.kafka.connect.transforms.RegexRouter",
    "transforms.order_items.regex": "(.*)\\.public\\.order_items",
    "transforms.order_items.replacement": "cdc-order-items",
}


def main() -> None:
    resp = httpx.put(
        f"{CONNECT_URL}/connectors/{CONNECTOR_NAME}/config",
        json=CONNECTOR_CONFIG,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        print(f"FAILED ({resp.status_code}): {resp.text}")
        sys.exit(1)

    action = "updated" if resp.status_code == 200 else "created"
    print(f"connector {CONNECTOR_NAME!r} {action}")
    print(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    main()
