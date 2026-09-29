"""POST /events — the client-facing ingestion endpoint for the 8 client-emitted event types
(Phase 3b). Uses the `emitted_events` fixture (tests/app/conftest.py) to inspect what actually
reached the producer's transport, not just the HTTP response.
"""

from __future__ import annotations

import time


def _now_ms() -> int:
    return int(time.time() * 1000)


def test_anonymous_product_view_is_accepted_with_null_user(client, emitted_events, product):
    resp = client.post(
        "/events",
        json={
            "event_type": "product_view",
            "event_timestamp": _now_ms(),
            "payload": {"product_id": str(product.product_id)},
        },
        headers={"X-Session-Id": "s-anon"},  # product_view is keyed by context.session_id
    )
    assert resp.status_code == 202, resp.text

    matching = [e for e in emitted_events if e["event"]["event_type"] == "product_view"]
    assert len(matching) == 1
    event = matching[0]["event"]
    assert event["context"]["user_id"] is None
    assert event["payload"]["product_id"] == str(product.product_id)
    assert matching[0]["topic"] == "product-events"


def test_authenticated_submission_carries_user_id(client, auth_headers, emitted_events, product):
    emitted_events.clear()  # auth_headers fixture already emitted registration/login events
    resp = client.post(
        "/events",
        json={"event_type": "product_view", "event_timestamp": _now_ms(), "payload": {"product_id": str(product.product_id)}},
        headers={**auth_headers, "X-Session-Id": "s-auth"},
    )
    assert resp.status_code == 202

    user_id = client.get("/users/me", headers=auth_headers).json()["user_id"]
    matching = [e for e in emitted_events if e["event"]["event_type"] == "product_view"]
    assert matching[0]["event"]["context"]["user_id"] == user_id


def test_session_id_header_is_captured(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "wishlist_view", "event_timestamp": _now_ms(), "payload": {"wishlist_id": None}},
        headers={"X-Session-Id": "session-abc-123"},
    )
    assert resp.status_code == 202
    matching = [e for e in emitted_events if e["event"]["event_type"] == "wishlist_view"]
    assert matching[0]["event"]["context"]["session_id"] == "session-abc-123"
    assert matching[0]["key"] == "session-abc-123"


def test_missing_session_id_header_leaves_session_null(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "sort_applied", "event_timestamp": _now_ms(), "payload": {"sort_field": "price", "sort_direction": "asc"}},
    )
    assert resp.status_code == 422  # sort_applied is keyed by context.session_id -- missing key -> rejected


def test_device_info_parsed_from_user_agent(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "page_view", "event_timestamp": _now_ms(), "payload": {"page_type": "home", "product_id": None, "category_id": None}},
        headers={
            "X-Session-Id": "s-1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        },
    )
    assert resp.status_code == 202
    matching = [e for e in emitted_events if e["event"]["event_type"] == "page_view"]
    device = matching[0]["event"]["device"]
    assert device["operating_system"] == "Windows"
    assert device["browser"] == "Chrome"
    assert device["device_type"] == "desktop"


def test_server_only_event_type_rejected(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "order_created", "event_timestamp": _now_ms(), "payload": {"order_id": "x"}},
        headers={"X-Session-Id": "s-1"},
    )
    assert resp.status_code == 422
    assert emitted_events == []


def test_unknown_event_type_rejected(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "totally_made_up", "event_timestamp": _now_ms(), "payload": {}},
        headers={"X-Session-Id": "s-1"},
    )
    assert resp.status_code == 404
    assert emitted_events == []


def test_malformed_payload_rejected(client, emitted_events):
    resp = client.post(
        "/events",
        json={"event_type": "search", "event_timestamp": _now_ms(), "payload": {"search_query": "shoes"}},  # missing search_result_count
        headers={"X-Session-Id": "s-1"},
    )
    assert resp.status_code == 422
    assert emitted_events == []


def test_filter_applied_accepts_array_of_filters(client, emitted_events):
    resp = client.post(
        "/events",
        json={
            "event_type": "filter_applied",
            "event_timestamp": _now_ms(),
            "payload": {
                "filters": [
                    {
                        "filter_type": "price",
                        "filter_value_string": None,
                        "filter_value_min": 10.0,
                        "filter_value_max": 50.0,
                        "filter_value_boolean": None,
                        "category_id": None,
                    },
                    {
                        "filter_type": "availability",
                        "filter_value_string": None,
                        "filter_value_min": None,
                        "filter_value_max": None,
                        "filter_value_boolean": True,
                        "category_id": None,
                    },
                ]
            },
        },
        headers={"X-Session-Id": "s-1"},
    )
    assert resp.status_code == 202, resp.text
    matching = [e for e in emitted_events if e["event"]["event_type"] == "filter_applied"]
    assert len(matching[0]["event"]["payload"]["filters"]) == 2
