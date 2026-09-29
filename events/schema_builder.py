"""Builds the 18 event `.avsc` files from shared envelope pieces, so the envelope/context/
device shape (MASTER_BUILD_PROMPT.md §28) is defined once instead of hand-copied into every
file. Run as `python -m events.schema_builder` to (re)materialize events/schemas/*.avsc — the
generated files are the actual contract artifacts (what registry.py loads at runtime, and what
Phase 4 registers into the real Schema Registry), not something re-run automatically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"

NS_COMMON = "ekadai.events.common"
NS_EVENTS = "ekadai.events"


def nullable_string() -> list:
    return ["null", "string"]


def decimal_type(precision: int = 18, scale: int = 2) -> dict:
    """Avro's real decimal logical type (exact, never float) — matches Postgres
    NUMERIC(18,2) precision/scale exactly (§11: never use floating point for money)."""
    return {"type": "bytes", "logicalType": "decimal", "precision": precision, "scale": scale}


def field(name: str, type_: Any, *, nullable: bool = False, doc: str | None = None) -> dict:
    f: dict = {"name": name}
    if nullable:
        f["type"] = ["null", type_] if not isinstance(type_, list) else type_
        f["default"] = None
    else:
        f["type"] = type_
    if doc:
        f["doc"] = doc
    return f


def record(name: str, namespace: str, fields: list[dict], doc: str | None = None) -> dict:
    r = {"type": "record", "name": name, "namespace": namespace, "fields": fields}
    if doc:
        r["doc"] = doc
    return r


CONTEXT_FIELD = field(
    "context",
    record(
        "EventContext",
        NS_COMMON,
        [
            field("user_id", "string", nullable=True),
            field("session_id", "string", nullable=True),
        ],
    ),
)

DEVICE_FIELD = field(
    "device",
    record(
        "DeviceInfo",
        NS_COMMON,
        [
            field("device_type", "string", nullable=True),
            field("operating_system", "string", nullable=True),
            field("browser", "string", nullable=True),
        ],
    ),
)


def build_event_schema(
    event_type: str,
    record_name: str,
    namespace: str,
    payload_fields: list[dict],
    doc: str,
) -> dict:
    payload = field("payload", record(f"{record_name}Payload", namespace, payload_fields))
    return record(
        record_name,
        namespace,
        [
            field("event_id", {"type": "string", "logicalType": "uuid"}),
            field("event_type", "string"),
            field("schema_version", "int"),
            field("event_timestamp", {"type": "long", "logicalType": "timestamp-millis"}),
            field("producer", "string"),
            CONTEXT_FIELD,
            DEVICE_FIELD,
            payload,
        ],
        doc=doc,
    )


FILTER_ENTRY = record(
    "FilterEntry",
    f"{NS_EVENTS}.product",
    [
        field("filter_type", "string", doc="brand | category | price | rating | availability"),
        field("filter_value_string", "string", nullable=True),
        field("filter_value_min", "double", nullable=True),
        field("filter_value_max", "double", nullable=True),
        field("filter_value_boolean", "boolean", nullable=True),
        field("category_id", "string", nullable=True),
    ],
)

# (event_type, topic, key_source, record_name, namespace, payload_fields, doc)
EVENT_DEFINITIONS: list[tuple[str, str, str, str, str, list[dict], str]] = [
    # --- user-events (key: context.user_id) — §29 ---
    (
        "user_registered",
        "user-events",
        "context.user_id",
        "UserRegistered",
        f"{NS_EVENTS}.user",
        [field("registration", record("Registration", f"{NS_EVENTS}.user", [field("registration_method", "string")]))],
        "Emitted once, at successful registration.",
    ),
    (
        "user_login",
        "user-events",
        "context.user_id",
        "UserLogin",
        f"{NS_EVENTS}.user",
        [field("authentication", record("Authentication", f"{NS_EVENTS}.user", [field("login_method", "string")]))],
        "Emitted on successful login.",
    ),
    (
        "user_logout",
        "user-events",
        "context.user_id",
        "UserLogout",
        f"{NS_EVENTS}.user",
        [],
        "Empty payload — logout is a stateless client action, envelope carries the signal.",
    ),
    # --- product-events (key: context.session_id) — §30, all Phase 3b (client-emitted) ---
    (
        "page_view",
        "product-events",
        "context.session_id",
        "PageView",
        f"{NS_EVENTS}.product",
        [
            field("page_type", "string", doc="home|category|product_listing|product_detail|cart|checkout|orders|profile|wishlist"),
            field("product_id", "string", nullable=True),
            field("category_id", "string", nullable=True),
        ],
        "Phase 3b (client-emitted). Do not auto-attach product_id to every page view.",
    ),
    (
        "search",
        "product-events",
        "context.session_id",
        "Search",
        f"{NS_EVENTS}.product",
        [field("search_query", "string"), field("search_result_count", "int")],
        "Phase 3b (client-emitted). Only on explicit submit, never per keystroke.",
    ),
    (
        "filter_applied",
        "product-events",
        "context.session_id",
        "FilterApplied",
        f"{NS_EVENTS}.product",
        [field("filters", {"type": "array", "items": FILTER_ENTRY})],
        "Phase 3b (client-emitted). One event may carry multiple filters.",
    ),
    (
        "sort_applied",
        "product-events",
        "context.session_id",
        "SortApplied",
        f"{NS_EVENTS}.product",
        [field("sort_field", "string", doc="price|rating|popularity|newest"), field("sort_direction", "string", doc="asc|desc")],
        "Phase 3b (client-emitted).",
    ),
    (
        "product_view",
        "product-events",
        "context.session_id",
        "ProductView",
        f"{NS_EVENTS}.product",
        [field("product_id", "string")],
        "Phase 3b (client-emitted) — React Query caching means this cannot be derived from GET /products/{id} server-side.",
    ),
    # --- cart-events — §31/§32 ---
    (
        "add_to_cart",
        "cart-events",
        "payload.cart_id",
        "AddToCart",
        f"{NS_EVENTS}.cart",
        [
            field("cart_id", "string"),
            field("product_id", "string"),
            field("quantity_added", "int"),
            field("cart_quantity_after", "int"),
        ],
        "Server-emitted. quantity_added > 0 always (delta=0 never reaches here).",
    ),
    (
        "remove_from_cart",
        "cart-events",
        "payload.cart_id",
        "RemoveFromCart",
        f"{NS_EVENTS}.cart",
        [
            field("cart_id", "string"),
            field("product_id", "string"),
            field("quantity_removed", "int"),
            field("cart_quantity_after", "int"),
        ],
        "Server-emitted. quantity_removed > 0 always.",
    ),
    (
        "wishlist_added",
        "cart-events",
        "context.user_id",
        "WishlistAdded",
        f"{NS_EVENTS}.cart",
        [field("wishlist_id", "string"), field("product_id", "string")],
        "Server-emitted. Keyed by user_id — wishlist has no cart_id and is 1:1 with the user.",
    ),
    (
        "wishlist_removed",
        "cart-events",
        "context.user_id",
        "WishlistRemoved",
        f"{NS_EVENTS}.cart",
        [field("wishlist_id", "string"), field("product_id", "string")],
        "Server-emitted. Keyed by user_id.",
    ),
    (
        "wishlist_view",
        "cart-events",
        "context.session_id",
        "WishlistView",
        f"{NS_EVENTS}.cart",
        [field("wishlist_id", "string", nullable=True)],
        "Phase 3b (client-emitted).",
    ),
    (
        "buy_now_clicked",
        "cart-events",
        "payload.checkout_id",
        "BuyNowClicked",
        f"{NS_EVENTS}.cart",
        [
            field("product_id", "string"),
            field("checkout_id", "string"),
            field("source", "string", doc="product_detail|wishlist|search_results|product_listing"),
        ],
        "Phase 3b (client-emitted) — no 'Buy Now' UI exists yet, contract defined for completeness.",
    ),
    # --- checkout-events — §33 ---
    (
        "checkout_started",
        "checkout-events",
        "payload.checkout_id",
        "CheckoutStarted",
        f"{NS_EVENTS}.checkout",
        [
            field("checkout_id", "string"),
            # Nullable since Phase 2c's Buy Now bypasses the cart entirely (§32) — no
            # cart_id exists for that flow.
            field("cart_id", "string", nullable=True),
            field("item_count", "int"),
            field("total_quantity", "int"),
            field("gross_merchandise_value", decimal_type()),
            field("discount_amount", decimal_type()),
            field("cart_net_value", decimal_type()),
            field("currency", "string"),
        ],
        "Server-emitted, from POST /checkout/start's already-computed snapshot.",
    ),
    # --- order-events — §35 ---
    (
        "order_created",
        "order-events",
        "payload.order_id",
        "OrderCreated",
        f"{NS_EVENTS}.order",
        [
            field("order_id", "string"),
            field("checkout_id", "string"),
            field("item_count", "int"),
            field("total_quantity", "int"),
            field("order_value", decimal_type()),
        ],
        "Server-emitted. Behavioral milestone only — NOT authoritative for order state (CDC is).",
    ),
    (
        "order_viewed",
        "order-events",
        "payload.order_id",
        "OrderViewed",
        f"{NS_EVENTS}.order",
        [field("order_id", "string"), field("page_context", "string")],
        "Phase 3b (client-emitted).",
    ),
    (
        "order_cancel_clicked",
        "order-events",
        "payload.order_id",
        "OrderCancelClicked",
        f"{NS_EVENTS}.order",
        [field("order_id", "string")],
        "Server-emitted, fired on request receipt — the click reaching the system, not the outcome.",
    ),
]


def generate_all() -> None:
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for event_type, topic, key_source, record_name, namespace, payload_fields, doc in EVENT_DEFINITIONS:
        schema = build_event_schema(event_type, record_name, namespace, payload_fields, doc)
        out_path = SCHEMAS_DIR / f"{event_type}.avsc"
        out_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_path.relative_to(SCHEMAS_DIR.parent.parent)}")


if __name__ == "__main__":
    generate_all()
