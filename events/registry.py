"""EVENT_TYPES: event_type -> routing metadata + parsed Avro schema.

`key_source` tells the producer where to find this event's Kafka partition key (§39): either
a dotted path into `context` (available on every event) or into `payload` (event-specific
fields like cart_id/checkout_id/order_id that don't belong in the common envelope).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastavro.schema import parse_schema

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"


@dataclass(frozen=True)
class EventTypeInfo:
    event_type: str
    topic: str
    key_source: str  # e.g. "context.user_id" or "payload.cart_id"
    schema: dict[str, Any]  # fastavro-parsed schema, ready for validation/serialization


def _load(event_type: str, topic: str, key_source: str) -> EventTypeInfo:
    raw = json.loads((SCHEMAS_DIR / f"{event_type}.avsc").read_text(encoding="utf-8"))
    return EventTypeInfo(event_type=event_type, topic=topic, key_source=key_source, schema=parse_schema(raw))


# (event_type, topic, key_source) — must match events/schema_builder.py's EVENT_DEFINITIONS.
_DEFINITIONS: list[tuple[str, str, str]] = [
    ("user_registered", "user-events", "context.user_id"),
    ("user_login", "user-events", "context.user_id"),
    ("user_logout", "user-events", "context.user_id"),
    ("page_view", "product-events", "context.session_id"),
    ("search", "product-events", "context.session_id"),
    ("filter_applied", "product-events", "context.session_id"),
    ("sort_applied", "product-events", "context.session_id"),
    ("product_view", "product-events", "context.session_id"),
    ("add_to_cart", "cart-events", "payload.cart_id"),
    ("remove_from_cart", "cart-events", "payload.cart_id"),
    ("wishlist_added", "cart-events", "context.user_id"),
    ("wishlist_removed", "cart-events", "context.user_id"),
    ("wishlist_view", "cart-events", "context.session_id"),
    ("buy_now_clicked", "cart-events", "payload.checkout_id"),
    ("checkout_started", "checkout-events", "payload.checkout_id"),
    ("order_created", "order-events", "payload.order_id"),
    ("order_viewed", "order-events", "payload.order_id"),
    ("order_cancel_clicked", "order-events", "payload.order_id"),
]

EVENT_TYPES: dict[str, EventTypeInfo] = {
    event_type: _load(event_type, topic, key_source) for event_type, topic, key_source in _DEFINITIONS
}

# The 8 event types that only make sense as client-originated signals (§30-§32, §35) — see
# Phase 3a/3b design notes for why (React Query caching means views can't be derived
# server-side). Everything else is wired server-side and must never be forgeable through the
# client-facing ingestion endpoint.
CLIENT_EMITTABLE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "page_view",
        "search",
        "filter_applied",
        "sort_applied",
        "product_view",
        "wishlist_view",
        "order_viewed",
        "buy_now_clicked",
    }
)


def resolve_key(event_type: str, envelope: dict[str, Any]) -> str:
    info = EVENT_TYPES[event_type]
    section, field_name = info.key_source.split(".")
    value = envelope[section][field_name]
    if value is None:
        raise ValueError(f"{event_type}: key field {info.key_source} is required but was None")
    return str(value)
