"""Tests for databricks/silver_rules.py (Phase 7 Silver validation).

Every test envelope takes the same path real data does: built by the app's own
`build_envelope`, Avro-encoded with the real registered schema, Avro-decoded, then serialized
exactly the way Bronze stores `raw_payload` (timestamp-millis as epoch ms, decimals and UUIDs as
strings) and parsed back — so the rules are tested against what Silver actually reads.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastavro import schemaless_reader, schemaless_writer

from events.envelope import EventContext
from events.producer import build_envelope
from events.registry import EVENT_TYPES, _DEFINITIONS

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "databricks"))
import silver_rules  # noqa: E402
from silver_rules import BUSINESS_RULE, MALFORMED, SCHEMA_INVALID, validate_event  # noqa: E402


def _bronze_json_default(value):
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, (Decimal, uuid.UUID)):
        return str(value)
    raise TypeError(type(value))


def as_bronze(event_type: str, payload: dict, context: EventContext | None = None) -> dict:
    """Envelope as it appears after Kafka -> Avro decode -> Bronze raw_payload JSON."""
    env = build_envelope(event_type, payload, context or EventContext(user_id=str(uuid.uuid4()), session_id="s-1"))
    schema = EVENT_TYPES[event_type].schema
    buf = io.BytesIO()
    schemaless_writer(buf, schema, env)
    buf.seek(0)
    decoded = schemaless_reader(buf, schema)
    return json.loads(json.dumps(decoded, default=_bronze_json_default))


def topic(event_type: str) -> str:
    return EVENT_TYPES[event_type].topic


def uid() -> str:
    return str(uuid.uuid4())


def filt(ftype, s=None, lo=None, hi=None, b=None, cat=None) -> dict:
    return {
        "filter_type": ftype,
        "filter_value_string": s,
        "filter_value_min": lo,
        "filter_value_max": hi,
        "filter_value_boolean": b,
        "category_id": cat,
    }


VALID_PAYLOADS = {
    "user_registered": {"registration": {"registration_method": "email"}},
    "user_login": {"authentication": {"login_method": "password"}},
    "user_logout": {},
    "page_view": {"page_type": "product_detail", "product_id": uid(), "category_id": None},
    "search": {"search_query": "earbuds", "search_result_count": 3},
    "filter_applied": {"filters": [filt("price", lo=100.0, hi=2000.0), filt("availability", b=True)]},
    "sort_applied": {"sort_field": "price", "sort_direction": "asc"},
    "product_view": {"product_id": uid()},
    "add_to_cart": {"cart_id": uid(), "product_id": uid(), "quantity_added": 2, "cart_quantity_after": 3},
    "remove_from_cart": {"cart_id": uid(), "product_id": uid(), "quantity_removed": 1, "cart_quantity_after": 0},
    "wishlist_added": {"wishlist_id": uid(), "product_id": uid()},
    "wishlist_removed": {"wishlist_id": uid(), "product_id": uid()},
    "wishlist_view": {"wishlist_id": uid()},
    "buy_now_clicked": {"product_id": uid(), "checkout_id": uid(), "source": "product_detail"},
    "checkout_started": {
        "checkout_id": uid(), "cart_id": uid(), "item_count": 2, "total_quantity": 3,
        "gross_merchandise_value": Decimal("3000.00"), "discount_amount": Decimal("300.00"),
        "cart_net_value": Decimal("2700.00"), "currency": "INR",
    },
    "order_created": {"order_id": uid(), "checkout_id": uid(), "item_count": 2, "total_quantity": 3, "order_value": Decimal("2700.00")},
    "order_viewed": {"order_id": uid(), "page_context": "order_detail"},
    "order_cancel_clicked": {"order_id": uid()},
}


def test_routing_matches_the_app_registry():
    assert silver_rules.EVENT_ROUTING == {et: (t, k) for et, t, k in _DEFINITIONS}


def test_every_event_type_has_a_valid_example():
    assert set(VALID_PAYLOADS) == set(EVENT_TYPES)


@pytest.mark.parametrize("event_type", sorted(VALID_PAYLOADS))
def test_valid_event_passes(event_type):
    env = as_bronze(event_type, VALID_PAYLOADS[event_type])
    result = validate_event(env, None, topic(event_type))
    assert result["error_type"] is None, result["errors"]
    assert result["fields"]["event_id"] == env["event_id"]
    assert isinstance(result["fields"]["event_timestamp_ms"], int)


def test_extracted_fields_for_checkout_started():
    env = as_bronze("checkout_started", VALID_PAYLOADS["checkout_started"])
    fields = validate_event(env, None, "checkout-events")["fields"]
    assert fields["gross_merchandise_value"] == "3000.00"
    assert fields["cart_net_value"] == "2700.00"
    assert fields["currency"] == "INR"
    assert fields["checkout_id"] == VALID_PAYLOADS["checkout_started"]["checkout_id"]
    assert fields["source_system"] == "ekadai-backend"
    assert fields["session_id"] == "s-1"


# --- MALFORMED -----------------------------------------------------------------------------

def test_decode_error_is_malformed():
    result = validate_event(None, "unknown schema id 999", "user-events")
    assert result["error_type"] == MALFORMED
    assert result["errors"] == ["unknown schema id 999"]


def test_non_object_payload_is_malformed():
    assert validate_event(["not", "an", "object"], None, "user-events")["error_type"] == MALFORMED


# --- SCHEMA_INVALID ------------------------------------------------------------------------

def test_unknown_event_type():
    env = as_bronze("product_view", VALID_PAYLOADS["product_view"])
    env["event_type"] = "made_up"
    assert validate_event(env, None, "product-events")["error_type"] == SCHEMA_INVALID


def test_bad_event_id():
    env = as_bronze("product_view", VALID_PAYLOADS["product_view"])
    env["event_id"] = "not-a-uuid"
    assert validate_event(env, None, "product-events")["error_type"] == SCHEMA_INVALID


def test_missing_timestamp():
    env = as_bronze("product_view", VALID_PAYLOADS["product_view"])
    env["event_timestamp"] = None
    assert validate_event(env, None, "product-events")["error_type"] == SCHEMA_INVALID


def test_wrong_topic():
    env = as_bronze("product_view", VALID_PAYLOADS["product_view"])
    result = validate_event(env, None, "order-events")
    assert result["error_type"] == SCHEMA_INVALID
    assert "belongs on product-events" in result["errors"][0]


def test_missing_partition_key():
    env = as_bronze("product_view", VALID_PAYLOADS["product_view"], EventContext(user_id=uid(), session_id=None))
    result = validate_event(env, None, "product-events")
    assert result["error_type"] == SCHEMA_INVALID
    assert "context.session_id" in result["errors"][0]


# --- BUSINESS_RULE -------------------------------------------------------------------------

@pytest.mark.parametrize(
    "event_type,override",
    [
        ("add_to_cart", {"quantity_added": 0}),
        ("add_to_cart", {"cart_quantity_after": -1}),
        ("remove_from_cart", {"quantity_removed": 0}),
        ("search", {"search_query": "   "}),
        ("search", {"search_result_count": -2}),
        ("checkout_started", {"item_count": 0}),
        ("checkout_started", {"gross_merchandise_value": Decimal("-1.00")}),
        ("checkout_started", {"discount_amount": Decimal("4000.00")}),
        ("checkout_started", {"cart_net_value": Decimal("2600.00")}),
        ("checkout_started", {"currency": "inr"}),
        ("order_created", {"order_value": Decimal("-5.00")}),
        ("filter_applied", {"filters": []}),
    ],
)
def test_business_rule_violations(event_type, override):
    payload = {**VALID_PAYLOADS[event_type], **override}
    result = validate_event(as_bronze(event_type, payload), None, topic(event_type))
    assert result["error_type"] == BUSINESS_RULE, result


def test_boolean_is_not_a_quantity():
    env = as_bronze("add_to_cart", VALID_PAYLOADS["add_to_cart"])
    env["payload"]["quantity_added"] = True
    assert validate_event(env, None, "cart-events")["error_type"] == BUSINESS_RULE


# --- §68 filter rules ------------------------------------------------------------------------

@pytest.mark.parametrize(
    "f",
    [
        filt("brand", s="Sonave"),
        filt("category", cat=uid()),
        filt("price", lo=100.0),
        filt("price", hi=500.0),
        filt("price", lo=100.0, hi=100.0),
        filt("rating", lo=4.0, hi=5.0),
        filt("availability", b=True),
        filt("availability", b=False),
    ],
)
def test_valid_filters(f):
    env = as_bronze("filter_applied", {"filters": [f]})
    assert validate_event(env, None, "product-events")["error_type"] is None


@pytest.mark.parametrize(
    "f,expected_fragment",
    [
        (filt("brand", s=""), "non-empty filter_value_string"),
        (filt("category", cat="not-a-uuid"), "valid category_id"),
        (filt("price"), "at least one of min/max"),
        (filt("price", lo=500.0, hi=100.0), "min 500.0 > max 100.0"),
        (filt("price", lo=-1.0), "must be >= 0"),
        (filt("rating", lo=3.0, hi=6.0), "within 0-5"),
        (filt("availability"), "needs filter_value_boolean"),
        (filt("brand", s="Sonave", lo=10.0), "must not populate filter_value_min"),
        (filt("category", cat=uid(), s="Electronics"), "must not populate filter_value_string"),
        (filt("colour", s="red"), "is not one of"),
    ],
)
def test_invalid_filters(f, expected_fragment):
    env = as_bronze("filter_applied", {"filters": [filt("availability", b=True), f]})
    result = validate_event(env, None, "product-events")
    assert result["error_type"] == BUSINESS_RULE
    assert any(expected_fragment in e for e in result["errors"]), result["errors"]
