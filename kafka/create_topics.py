"""Idempotently creates the 10 Kafka topics with the exact partition counts from
MASTER_BUILD_PROMPT.md §38-39. Topic names come from `events.registry.EVENT_TYPES` (the single
source of truth already used by the producer) rather than being duplicated here; only the
partition count per topic — which `events/registry.py` has no reason to know about — is
declared locally.

Run as `python -m kafka.create_topics` against a running local broker (`kafka/docker-compose.yml`).
"""

from __future__ import annotations

import sys

from confluent_kafka.admin import AdminClient, NewTopic

from app.config import settings
from events.registry import EVENT_TYPES

# §39 — replication factor is 1 everywhere (single-broker local cluster).
TOPIC_PARTITIONS: dict[str, int] = {
    "user-events": 3,
    "product-events": 6,
    "cart-events": 4,
    "checkout-events": 4,
    "order-events": 3,
    "cdc-users": 3,
    "cdc-products": 6,
    "cdc-categories": 3,
    "cdc-orders": 3,
    "cdc-order-items": 3,
}


def behavioral_topics() -> set[str]:
    return {info.topic for info in EVENT_TYPES.values()}


def main() -> None:
    expected_topics = set(TOPIC_PARTITIONS)
    behavioral = behavioral_topics()
    missing_from_table = behavioral - expected_topics
    if missing_from_table:
        print(f"ERROR: topics referenced by events/registry.py but missing from TOPIC_PARTITIONS: {missing_from_table}")
        sys.exit(1)

    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap_servers})
    existing = set(admin.list_topics(timeout=10).topics.keys())

    to_create = [
        NewTopic(name, num_partitions=partitions, replication_factor=1)
        for name, partitions in TOPIC_PARTITIONS.items()
        if name not in existing
    ]

    if not to_create:
        print(f"All {len(TOPIC_PARTITIONS)} topics already exist — nothing to do.")
        return

    print(f"Creating {len(to_create)} topic(s): {[t.topic for t in to_create]}")
    futures = admin.create_topics(to_create)
    for topic, future in futures.items():
        try:
            future.result()
            print(f"  created {topic}")
        except Exception as exc:  # noqa: BLE001 — surfacing broker errors verbatim is the point
            print(f"  FAILED {topic}: {exc}")
            sys.exit(1)

    print(f"Done. {len(TOPIC_PARTITIONS)} topics total, {sum(TOPIC_PARTITIONS.values())} partitions.")


if __name__ == "__main__":
    main()
