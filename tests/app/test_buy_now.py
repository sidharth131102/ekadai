"""Buy Now (§32, Phase 2c): a genuine bypass of the cart, not add-to-cart-then-checkout —
the defining property under test is that an in-progress buy-now purchase never touches,
blocks on, or is affected by the user's existing cart.
"""

import uuid
from decimal import Decimal

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


class TestBuyNowCheckoutSnapshot:
    def test_snapshot_has_no_cart_id(self, client, auth_headers, product):
        resp = client.post(
            "/checkout/start",
            json={"buy_now": {"product_id": str(product.product_id), "quantity": 2}},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["cart_id"] is None
        assert body["total_quantity"] == 2
        assert Decimal(body["gross_merchandise_value"]) == Decimal("200.00")  # base_price=100.00

    def test_snapshot_without_body_still_works_cart_mode(self, client, auth_headers, product):
        # existing cart-mode behavior (no request body at all) must be unaffected
        client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 1}, headers=auth_headers)
        resp = client.post("/checkout/start", headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["cart_id"] is not None


class TestBuyNowOrderCreation:
    def test_buy_now_creates_order_for_just_that_product(self, client, auth_headers, product):
        address_id = _add_address(client, auth_headers)
        checkout_id = str(uuid.uuid4())
        client.post(
            "/checkout/start",
            json={"buy_now": {"product_id": str(product.product_id), "quantity": 3}},
            headers=auth_headers,
        )
        resp = client.post(
            "/orders",
            json={
                "checkout_id": checkout_id,
                "address_id": address_id,
                "buy_now": {"product_id": str(product.product_id), "quantity": 3},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        order = resp.json()
        assert order["item_count"] == 1
        assert order["total_quantity"] == 3
        assert Decimal(order["total_amount"]) == Decimal("300.00")

    def test_buy_now_does_not_touch_existing_cart(self, client, auth_headers, product, db_session, category):
        from db.models import Product

        other_product = Product(
            product_name=f"other-{uuid.uuid4()}",
            category_id=category.category_id,
            base_price=Decimal("50.00"),
            product_status="ACTIVE",
        )
        db_session.add(other_product)
        db_session.flush()

        # existing cart item, untouched by the upcoming buy-now purchase
        client.post(
            "/cart/items", json={"product_id": str(other_product.product_id), "quantity": 5}, headers=auth_headers
        )
        address_id = _add_address(client, auth_headers)

        resp = client.post(
            "/orders",
            json={
                "checkout_id": str(uuid.uuid4()),
                "address_id": address_id,
                "buy_now": {"product_id": str(product.product_id), "quantity": 1},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

        cart = client.get("/cart", headers=auth_headers).json()
        assert cart["items"][0]["product_id"] == str(other_product.product_id)
        assert cart["items"][0]["quantity"] == 5
        assert len(cart["items"]) == 1

    def test_buy_now_discontinued_product_rejected(self, client, auth_headers, db_session, product):
        product.product_status = "DISCONTINUED"
        db_session.flush()
        address_id = _add_address(client, auth_headers)

        resp = client.post(
            "/orders",
            json={
                "checkout_id": str(uuid.uuid4()),
                "address_id": address_id,
                "buy_now": {"product_id": str(product.product_id), "quantity": 1},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409

    def test_buy_now_idempotent_replay(self, client, auth_headers, product):
        address_id = _add_address(client, auth_headers)
        checkout_id = str(uuid.uuid4())
        body = {
            "checkout_id": checkout_id,
            "address_id": address_id,
            "buy_now": {"product_id": str(product.product_id), "quantity": 1},
        }
        first = client.post("/orders", json=body, headers=auth_headers)
        second = client.post("/orders", json=body, headers=auth_headers)
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["order_id"] == second.json()["order_id"]

    def test_buy_now_zero_quantity_rejected(self, client, auth_headers, product):
        address_id = _add_address(client, auth_headers)
        resp = client.post(
            "/orders",
            json={
                "checkout_id": str(uuid.uuid4()),
                "address_id": address_id,
                "buy_now": {"product_id": str(product.product_id), "quantity": 0},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422


def test_checkout_started_event_has_null_cart_id_for_buy_now(client, auth_headers, product, emitted_events):
    client.post(
        "/checkout/start",
        json={"buy_now": {"product_id": str(product.product_id), "quantity": 1}},
        headers=auth_headers,
    )
    matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "checkout_started"]
    assert len(matching) == 1
    assert matching[0]["payload"]["cart_id"] is None
