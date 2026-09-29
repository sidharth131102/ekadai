from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from events.envelope import EventContext
from events.producer import EventProducer


class CapturingTransport:
    def __init__(self):
        self.sent: list[tuple[str, str, dict]] = []

    def send(self, topic, key, event):
        self.sent.append((topic, key, event))


def test_emit_routes_to_correct_topic_and_key_from_context():
    transport = CapturingTransport()
    producer = EventProducer(transport)
    producer.emit("user_login", {"authentication": {"login_method": "email"}}, context=EventContext(user_id="u-1"))

    assert len(transport.sent) == 1
    topic, key, event = transport.sent[0]
    assert topic == "user-events"
    assert key == "u-1"
    assert event["event_type"] == "user_login"
    assert event["context"]["user_id"] == "u-1"


def test_emit_routes_to_correct_topic_and_key_from_payload():
    transport = CapturingTransport()
    producer = EventProducer(transport)
    producer.emit(
        "add_to_cart",
        {"cart_id": "cart-42", "product_id": "p-1", "quantity_added": 1, "cart_quantity_after": 1},
    )

    topic, key, _event = transport.sent[0]
    assert topic == "cart-events"
    assert key == "cart-42"


def test_emit_never_raises_on_invalid_payload():
    transport = CapturingTransport()
    producer = EventProducer(transport)
    # missing required fields -- emit() must swallow the validation error, not raise
    producer.emit("add_to_cart", {"cart_id": "c-1"})
    assert transport.sent == []  # never reached the transport


def test_emit_never_raises_when_key_field_is_missing():
    transport = CapturingTransport()
    producer = EventProducer(transport)
    # context.user_id required as the key for user-events but not supplied
    producer.emit("user_login", {"authentication": {"login_method": "email"}})
    assert transport.sent == []


def test_checkout_started_carries_exact_decimal_values():
    transport = CapturingTransport()
    producer = EventProducer(transport)
    producer.emit(
        "checkout_started",
        {
            "checkout_id": "co-1",
            "cart_id": "c-1",
            "item_count": 1,
            "total_quantity": 3,
            "gross_merchandise_value": Decimal("300.00"),
            "discount_amount": Decimal("30.00"),
            "cart_net_value": Decimal("270.00"),
            "currency": "USD",
        },
    )
    _topic, key, event = transport.sent[0]
    assert key == "co-1"
    assert event["payload"]["gross_merchandise_value"] == Decimal("300.00")
