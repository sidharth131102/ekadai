"""Every event type: a correct sample payload validates against its own .avsc, and an
obviously-wrong one is rejected — proves the contract is real, not decorative."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from events.producer import build_envelope, validate
from events.registry import EVENT_TYPES

SAMPLE_PAYLOADS: dict[str, dict] = {
    "user_registered": {"registration": {"registration_method": "email"}},
    "user_login": {"authentication": {"login_method": "email"}},
    "user_logout": {},
    "page_view": {"page_type": "product_detail", "product_id": "p-1", "category_id": None},
    "search": {"search_query": "wireless earbuds", "search_result_count": 12},
    "filter_applied": {
        "filters": [
            {
                "filter_type": "price",
                "filter_value_string": None,
                "filter_value_min": 10.0,
                "filter_value_max": 100.0,
                "filter_value_boolean": None,
                "category_id": None,
            }
        ]
    },
    "sort_applied": {"sort_field": "price", "sort_direction": "asc"},
    "product_view": {"product_id": "p-1"},
    "add_to_cart": {"cart_id": "c-1", "product_id": "p-1", "quantity_added": 2, "cart_quantity_after": 2},
    "remove_from_cart": {"cart_id": "c-1", "product_id": "p-1", "quantity_removed": 1, "cart_quantity_after": 1},
    "wishlist_added": {"wishlist_id": "w-1", "product_id": "p-1"},
    "wishlist_removed": {"wishlist_id": "w-1", "product_id": "p-1"},
    "wishlist_view": {"wishlist_id": "w-1"},
    "buy_now_clicked": {"product_id": "p-1", "checkout_id": "co-1", "source": "product_detail"},
    "checkout_started": {
        "checkout_id": "co-1",
        "cart_id": "c-1",
        "item_count": 1,
        "total_quantity": 2,
        "gross_merchandise_value": Decimal("100.00"),
        "discount_amount": Decimal("10.00"),
        "cart_net_value": Decimal("90.00"),
        "currency": "USD",
    },
    "order_created": {
        "order_id": "o-1",
        "checkout_id": "co-1",
        "item_count": 1,
        "total_quantity": 2,
        "order_value": Decimal("90.00"),
    },
    "order_viewed": {"order_id": "o-1", "page_context": "order_details"},
    "order_cancel_clicked": {"order_id": "o-1"},
}


def test_every_event_type_has_a_sample() -> None:
    assert set(SAMPLE_PAYLOADS.keys()) == set(EVENT_TYPES.keys())


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES.keys()))
def test_sample_payload_validates(event_type: str) -> None:
    envelope = build_envelope(event_type, SAMPLE_PAYLOADS[event_type])
    validate(event_type, envelope)  # must not raise


# One genuinely-required (non-nullable, no default) payload field per event type, to drop
# for the negative test below. Events with an empty or all-nullable payload have none.
REQUIRED_FIELD_TO_DROP: dict[str, str] = {
    "user_registered": "registration",
    "user_login": "authentication",
    "page_view": "page_type",
    "search": "search_query",
    "filter_applied": "filters",
    "sort_applied": "sort_field",
    "product_view": "product_id",
    "add_to_cart": "cart_id",
    "remove_from_cart": "cart_id",
    "wishlist_added": "wishlist_id",
    "wishlist_removed": "wishlist_id",
    "buy_now_clicked": "product_id",
    "checkout_started": "checkout_id",
    "order_created": "order_id",
    "order_viewed": "order_id",
    "order_cancel_clicked": "order_id",
    # user_logout: empty payload. wishlist_view: payload is entirely nullable fields.
    # Neither has a field whose absence Avro would reject.
}


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES.keys()))
def test_missing_required_payload_field_is_rejected(event_type: str) -> None:
    field_to_drop = REQUIRED_FIELD_TO_DROP.get(event_type)
    if field_to_drop is None:
        pytest.skip(f"{event_type} has no required payload field to omit")
    truncated = {k: v for k, v in SAMPLE_PAYLOADS[event_type].items() if k != field_to_drop}
    envelope = build_envelope(event_type, truncated)
    with pytest.raises(ValueError):
        validate(event_type, envelope)


def test_wrong_type_in_payload_is_rejected() -> None:
    envelope = build_envelope("add_to_cart", {"cart_id": "c-1", "product_id": "p-1", "quantity_added": "two", "cart_quantity_after": 2})
    with pytest.raises(ValueError):
        validate("add_to_cart", envelope)
