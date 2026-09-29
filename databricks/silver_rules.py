"""Phase 7 — Silver validation rules for behavioral events (§54, §59, §64, §68).

Pure Python, no Spark: the pipeline calls `validate_event` from a UDF, and the same function is
unit-tested locally (tests/databricks/test_silver_rules.py). Input is a decoded Bronze envelope
(the parsed `raw_payload` dict, or None if Bronze couldn't decode the message); output is a
verdict plus the §54 fields extracted from it.

Error types written to `silver_event_quarantine.error_type`:
- MALFORMED       — Bronze couldn't decode the message, or the payload isn't a JSON object.
- SCHEMA_INVALID  — envelope fields missing/wrong, unknown event type, event on the wrong topic,
                    or the topic's partition key (§39) absent.
- BUSINESS_RULE   — structurally fine but semantically impossible (non-positive quantities,
                    negative money, net ≠ gross − discount, §68 filter rules, …).
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

MALFORMED = "MALFORMED"
SCHEMA_INVALID = "SCHEMA_INVALID"
BUSINESS_RULE = "BUSINESS_RULE"

# event_type -> (topic, partition-key path). Mirrors events/registry.py's _DEFINITIONS — a test
# asserts the two stay identical, since this module can't import the app package on Databricks.
EVENT_ROUTING: dict[str, tuple[str, str]] = {
    "user_registered": ("user-events", "context.user_id"),
    "user_login": ("user-events", "context.user_id"),
    "user_logout": ("user-events", "context.user_id"),
    "page_view": ("product-events", "context.session_id"),
    "search": ("product-events", "context.session_id"),
    "filter_applied": ("product-events", "context.session_id"),
    "sort_applied": ("product-events", "context.session_id"),
    "product_view": ("product-events", "context.session_id"),
    "add_to_cart": ("cart-events", "payload.cart_id"),
    "remove_from_cart": ("cart-events", "payload.cart_id"),
    "wishlist_added": ("cart-events", "context.user_id"),
    "wishlist_removed": ("cart-events", "context.user_id"),
    "wishlist_view": ("cart-events", "context.session_id"),
    "buy_now_clicked": ("cart-events", "payload.checkout_id"),
    "checkout_started": ("checkout-events", "payload.checkout_id"),
    "order_created": ("order-events", "payload.order_id"),
    "order_viewed": ("order-events", "payload.order_id"),
    "order_cancel_clicked": ("order-events", "payload.order_id"),
}

FILTER_FIELDS = ("filter_value_string", "filter_value_min", "filter_value_max", "filter_value_boolean", "category_id")
# filter_type -> the only fields it may populate (§68 "do not populate irrelevant fields").
FILTER_ALLOWED_FIELDS: dict[str, set[str]] = {
    "brand": {"filter_value_string"},
    "category": {"category_id"},
    "price": {"filter_value_min", "filter_value_max"},
    "rating": {"filter_value_min", "filter_value_max"},
    "availability": {"filter_value_boolean"},
}

_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _is_int(value: Any) -> bool:
    # bool is a subclass of int in Python — `True` must not pass as a quantity.
    return isinstance(value, int) and not isinstance(value, bool)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _validate_filter(index: int, f: Any) -> list[str]:
    if not isinstance(f, dict):
        return [f"filters[{index}] is not an object"]
    ftype = f.get("filter_type")
    allowed = FILTER_ALLOWED_FIELDS.get(ftype)
    if allowed is None:
        return [f"filters[{index}].filter_type {ftype!r} is not one of {sorted(FILTER_ALLOWED_FIELDS)}"]

    errors = [
        f"filters[{index}] ({ftype}) must not populate {name}"
        for name in FILTER_FIELDS
        if name not in allowed and f.get(name) is not None
    ]
    lo, hi = f.get("filter_value_min"), f.get("filter_value_max")

    if ftype == "brand" and not (isinstance(f.get("filter_value_string"), str) and f["filter_value_string"].strip()):
        errors.append(f"filters[{index}] (brand) needs a non-empty filter_value_string")
    elif ftype == "category" and not _is_uuid(f.get("category_id")):
        errors.append(f"filters[{index}] (category) needs a valid category_id")
    elif ftype == "availability" and not isinstance(f.get("filter_value_boolean"), bool):
        errors.append(f"filters[{index}] (availability) needs filter_value_boolean")
    elif ftype in ("price", "rating"):
        if lo is None and hi is None:
            errors.append(f"filters[{index}] ({ftype}) needs at least one of min/max")
        if lo is not None and hi is not None and lo > hi:
            errors.append(f"filters[{index}] ({ftype}) min {lo} > max {hi}")
        bounds = [v for v in (lo, hi) if v is not None]
        if ftype == "price" and any(v < 0 for v in bounds):
            errors.append(f"filters[{index}] (price) bounds must be >= 0")
        if ftype == "rating" and any(v < 0 or v > 5 for v in bounds):
            errors.append(f"filters[{index}] (rating) bounds must be within 0-5")
    return errors


def _business_errors(event_type: str, p: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def positive(name: str) -> None:
        v = p.get(name)
        if not _is_int(v) or v <= 0:
            errors.append(f"{name} must be a positive integer, got {v!r}")

    def non_negative(name: str) -> None:
        v = p.get(name)
        if not _is_int(v) or v < 0:
            errors.append(f"{name} must be a non-negative integer, got {v!r}")

    def money(name: str) -> Decimal | None:
        d = _decimal(p.get(name))
        if d is None or d < 0:
            errors.append(f"{name} must be a non-negative amount, got {p.get(name)!r}")
            return None
        return d

    def currency() -> None:
        if not (isinstance(p.get("currency"), str) and _CURRENCY.match(p["currency"])):
            errors.append(f"currency must be a 3-letter uppercase code, got {p.get('currency')!r}")

    if event_type == "add_to_cart":
        positive("quantity_added")
        non_negative("cart_quantity_after")
    elif event_type == "remove_from_cart":
        positive("quantity_removed")
        non_negative("cart_quantity_after")
    elif event_type == "search":
        if not (isinstance(p.get("search_query"), str) and p["search_query"].strip()):
            errors.append("search_query must be non-empty")
        non_negative("search_result_count")
    elif event_type == "checkout_started":
        positive("item_count")
        positive("total_quantity")
        gross, discount, net = money("gross_merchandise_value"), money("discount_amount"), money("cart_net_value")
        if None not in (gross, discount, net):
            if discount > gross:
                errors.append(f"discount_amount {discount} exceeds gross_merchandise_value {gross}")
            elif net != gross - discount:
                errors.append(f"cart_net_value {net} != gross_merchandise_value {gross} - discount_amount {discount}")
        currency()
    elif event_type == "order_created":
        positive("item_count")
        positive("total_quantity")
        money("order_value")
    elif event_type == "filter_applied":
        filters = p.get("filters")
        if not isinstance(filters, list) or not filters:
            errors.append("filters must be a non-empty list")
        else:
            for i, f in enumerate(filters):
                errors.extend(_validate_filter(i, f))
    return errors


def _extract(env: dict[str, Any]) -> dict[str, Any]:
    ctx = env.get("context") or {}
    dev = env.get("device") or {}
    p = env.get("payload") or {}
    return {
        "event_id": env.get("event_id"),
        "event_type": env.get("event_type"),
        "schema_version": env.get("schema_version"),
        "user_id": ctx.get("user_id"),
        "session_id": ctx.get("session_id"),
        "product_id": p.get("product_id"),
        "category_id": p.get("category_id"),
        "cart_id": p.get("cart_id"),
        "checkout_id": p.get("checkout_id"),
        "order_id": p.get("order_id"),
        "event_timestamp_ms": env.get("event_timestamp"),
        "device_type": dev.get("device_type"),
        "operating_system": dev.get("operating_system"),
        "browser": dev.get("browser"),
        "search_query": p.get("search_query"),
        "search_result_count": p.get("search_result_count"),
        "quantity_added": p.get("quantity_added"),
        "quantity_removed": p.get("quantity_removed"),
        "cart_quantity_after": p.get("cart_quantity_after"),
        "item_count": p.get("item_count"),
        "total_quantity": p.get("total_quantity"),
        "gross_merchandise_value": _str_or_none(p.get("gross_merchandise_value")),
        "discount_amount": _str_or_none(p.get("discount_amount")),
        "cart_net_value": _str_or_none(p.get("cart_net_value")),
        "order_value": _str_or_none(p.get("order_value")),
        "currency": p.get("currency"),
        "source": p.get("source"),
        "source_system": env.get("producer"),
        "filters": p.get("filters") if env.get("event_type") == "filter_applied" else None,
    }


def _str_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def validate_event(envelope: Any, decode_error: str | None, kafka_topic: str | None) -> dict[str, Any]:
    """Returns {"error_type": None | MALFORMED | SCHEMA_INVALID | BUSINESS_RULE,
    "errors": [str, ...], "fields": {...§54 fields, or {} if MALFORMED}}."""
    if decode_error is not None or not isinstance(envelope, dict):
        reason = decode_error or "payload is not a JSON object"
        return {"error_type": MALFORMED, "errors": [reason], "fields": {}}

    fields = _extract(envelope)
    errors: list[str] = []

    if not _is_uuid(fields["event_id"]):
        errors.append(f"event_id must be a UUID, got {fields['event_id']!r}")
    event_type = fields["event_type"]
    routing = EVENT_ROUTING.get(event_type)
    if routing is None:
        errors.append(f"unknown event_type {event_type!r}")
    if not _is_int(fields["schema_version"]) or fields["schema_version"] < 1:
        errors.append(f"schema_version must be an integer >= 1, got {fields['schema_version']!r}")
    ts = fields["event_timestamp_ms"]
    if not _is_int(ts) or ts <= 0:
        errors.append(f"event_timestamp must be positive epoch millis, got {ts!r}")
    if not isinstance(envelope.get("payload"), dict):
        errors.append("payload must be an object")

    if routing is not None:
        expected_topic, key_path = routing
        if kafka_topic is not None and kafka_topic != expected_topic:
            errors.append(f"{event_type} belongs on {expected_topic}, arrived on {kafka_topic}")
        section, key = key_path.split(".")
        if not (envelope.get(section) or {}).get(key):
            errors.append(f"partition key {key_path} is required for {event_type}")

    if errors:
        return {"error_type": SCHEMA_INVALID, "errors": errors, "fields": fields}

    business = _business_errors(event_type, envelope["payload"])
    if business:
        return {"error_type": BUSINESS_RULE, "errors": business, "fields": fields}
    return {"error_type": None, "errors": [], "fields": fields}
