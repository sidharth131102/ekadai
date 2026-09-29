import uuid
from decimal import Decimal

from tests.app.conftest import make_sitewide_promotion, register_and_login

ADDRESS_PAYLOAD = {
    "address_line1": "1 Main St",
    "city": "Metropolis",
    "state": "NY",
    "postal_code": "10001",
    "country": "US",
}


def _add_address(client, headers) -> str:
    resp = client.post("/users/me/addresses", json=ADDRESS_PAYLOAD, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["address_id"]


def _add_to_cart(client, headers, product, quantity=1):
    resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": quantity}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCheckoutSnapshot:
    def test_snapshot_without_promotion(self, client, auth_headers, product):
        _add_to_cart(client, auth_headers, product, quantity=3)  # base_price=100.00
        resp = client.post("/checkout/start", headers=auth_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["item_count"] == 1
        assert body["total_quantity"] == 3
        assert Decimal(body["gross_merchandise_value"]) == Decimal("300.00")
        assert Decimal(body["discount_amount"]) == Decimal("0.00")
        assert Decimal(body["cart_net_value"]) == Decimal("300.00")

    def test_snapshot_with_sitewide_percentage_promotion(self, client, auth_headers, db_session, product):
        make_sitewide_promotion(db_session, discount_type="PERCENTAGE", discount_value=Decimal("10.00"))
        _add_to_cart(client, auth_headers, product, quantity=3)  # 3 * 100.00 = 300.00

        resp = client.post("/checkout/start", headers=auth_headers)
        body = resp.json()
        assert Decimal(body["gross_merchandise_value"]) == Decimal("300.00")
        assert Decimal(body["discount_amount"]) == Decimal("30.00")
        assert Decimal(body["cart_net_value"]) == Decimal("270.00")

    def test_snapshot_empty_cart_rejected(self, client, auth_headers):
        resp = client.post("/checkout/start", headers=auth_headers)
        assert resp.status_code == 422


class TestOrderCreation:
    def test_happy_path_creates_confirmed_order(self, client, auth_headers, product):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=2)  # 2 * 100.00 = 200.00
        checkout_id = str(uuid.uuid4())

        resp = client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        order = resp.json()
        assert order["status"] == "CONFIRMED"
        assert order["checkout_id"] == checkout_id
        assert order["item_count"] == 1
        assert order["total_quantity"] == 2
        assert Decimal(order["total_amount"]) == Decimal("200.00")
        assert order["confirmed_at"] is not None
        assert order["cancelled_at"] is None
        assert len(order["items"]) == 1
        assert Decimal(order["items"][0]["line_revenue"]) == Decimal("200.00")

        # cart must now be checked out, not reusable
        cart_resp = client.get("/cart", headers=auth_headers)
        assert cart_resp.json()["items"] == []

    def test_order_applies_promotion_discount(self, client, auth_headers, db_session, product):
        make_sitewide_promotion(db_session, discount_type="PERCENTAGE", discount_value=Decimal("10.00"))
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=3)  # gross 300.00, 10% off

        resp = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id}, headers=auth_headers
        )
        order = resp.json()
        item = order["items"][0]
        assert Decimal(item["discount_amount"]) == Decimal("30.00")
        assert Decimal(item["line_revenue"]) == Decimal("270.00")
        assert Decimal(order["total_amount"]) == Decimal("270.00")

    def test_duplicate_checkout_id_replays_same_order(self, client, auth_headers, product):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=1)
        checkout_id = str(uuid.uuid4())

        first = client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        assert first.status_code == 201
        order_id = first.json()["order_id"]

        # cart is now checked out and empty -- re-submitting the same checkout_id must
        # still return the original order rather than 409/422.
        second = client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        assert second.status_code == 201
        assert second.json()["order_id"] == order_id

    def test_empty_cart_rejected(self, client, auth_headers):
        address_id = _add_address(client, auth_headers)
        resp = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id}, headers=auth_headers
        )
        assert resp.status_code == 409  # no ACTIVE cart at all

    def test_address_not_owned_by_user_rejected(self, client, product):
        headers_a, _ = register_and_login(client)
        headers_b, _ = register_and_login(client)
        address_id_b = _add_address(client, headers_b)
        _add_to_cart(client, headers_a, product, quantity=1)

        resp = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id_b}, headers=headers_a
        )
        assert resp.status_code == 404

    def test_discontinued_product_blocks_checkout(self, client, auth_headers, db_session, product):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=1)

        product.product_status = "DISCONTINUED"
        db_session.flush()

        resp = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id}, headers=auth_headers
        )
        assert resp.status_code == 409

    def test_order_history_and_detail_isolated_per_user(self, client, product):
        headers_a, _ = register_and_login(client)
        headers_b, _ = register_and_login(client)
        address_id_a = _add_address(client, headers_a)
        _add_to_cart(client, headers_a, product, quantity=1)
        created = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id_a}, headers=headers_a
        ).json()

        list_b = client.get("/orders", headers=headers_b).json()
        assert list_b["total"] == 0

        detail_b = client.get(f"/orders/{created['order_id']}", headers=headers_b)
        assert detail_b.status_code == 404

        detail_a = client.get(f"/orders/{created['order_id']}", headers=headers_a)
        assert detail_a.status_code == 200


class TestOrderCancellation:
    def _create_order(self, client, headers, product):
        address_id = _add_address(client, headers)
        _add_to_cart(client, headers, product, quantity=1)
        resp = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id}, headers=headers
        )
        return resp.json()

    def test_cancel_confirmed_order(self, client, auth_headers, product):
        order = self._create_order(client, auth_headers, product)
        resp = client.post(f"/orders/{order['order_id']}/cancel", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "CANCELLED"
        assert body["cancelled_at"] is not None

    def test_cancel_already_cancelled_order_rejected(self, client, auth_headers, product):
        order = self._create_order(client, auth_headers, product)
        client.post(f"/orders/{order['order_id']}/cancel", headers=auth_headers)
        resp = client.post(f"/orders/{order['order_id']}/cancel", headers=auth_headers)
        assert resp.status_code == 409

    def test_cancel_other_users_order_rejected(self, client, product):
        headers_a, _ = register_and_login(client)
        headers_b, _ = register_and_login(client)
        order = self._create_order(client, headers_a, product)

        resp = client.post(f"/orders/{order['order_id']}/cancel", headers=headers_b)
        assert resp.status_code == 404


class TestEventEmission:
    def test_checkout_start_emits_checkout_started_with_matching_totals(self, client, auth_headers, product, emitted_events):
        _add_to_cart(client, auth_headers, product, quantity=3)  # base_price=100.00 -> 300.00
        client.post("/checkout/start", headers=auth_headers)

        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "checkout_started"]
        assert len(matching) == 1
        payload = matching[0]["payload"]
        assert Decimal(payload["gross_merchandise_value"]) == Decimal("300.00")
        assert Decimal(payload["cart_net_value"]) == Decimal("300.00")

    def test_order_creation_emits_order_created_once(self, client, auth_headers, product, emitted_events):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=2)
        checkout_id = str(uuid.uuid4())
        emitted_events.clear()

        client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "order_created"]
        assert len(matching) == 1
        assert matching[0]["payload"]["checkout_id"] == checkout_id
        assert Decimal(matching[0]["payload"]["order_value"]) == Decimal("200.00")

    def test_duplicate_checkout_id_does_not_re_emit_order_created(self, client, auth_headers, product, emitted_events):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=1)
        checkout_id = str(uuid.uuid4())

        client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        emitted_events.clear()

        # replay of the same checkout_id -- must not fire a second order_created
        client.post("/orders", json={"checkout_id": checkout_id, "address_id": address_id}, headers=auth_headers)
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "order_created"]
        assert matching == []

    def test_cancel_emits_order_cancel_clicked_even_when_it_ultimately_fails(self, client, auth_headers, product, emitted_events):
        address_id = _add_address(client, auth_headers)
        _add_to_cart(client, auth_headers, product, quantity=1)
        order = client.post(
            "/orders", json={"checkout_id": str(uuid.uuid4()), "address_id": address_id}, headers=auth_headers
        ).json()
        client.post(f"/orders/{order['order_id']}/cancel", headers=auth_headers)  # first cancel succeeds
        emitted_events.clear()

        # second cancel attempt fails (already CANCELLED) but the click event still fires
        resp = client.post(f"/orders/{order['order_id']}/cancel", headers=auth_headers)
        assert resp.status_code == 409
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "order_cancel_clicked"]
        assert len(matching) == 1
        assert matching[0]["payload"]["order_id"] == order["order_id"]
