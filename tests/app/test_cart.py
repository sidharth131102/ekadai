from tests.app.conftest import register_and_login


def test_get_cart_empty_when_none_exists(client, auth_headers):
    resp = client.get("/cart", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] is None
    assert body["items"] == []


def test_add_item_creates_cart_lazily(client, auth_headers, product):
    resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["cart_id"] is not None
    assert body["total_quantity"] == 2
    assert body["items"][0]["quantity"] == 2


def test_add_item_twice_increments_quantity(client, auth_headers, product):
    client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers)
    resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": 3}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 5


def test_add_discontinued_product_rejected(client, auth_headers, db_session, product):
    product.product_status = "DISCONTINUED"
    db_session.flush()
    resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": 1}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_update_item_sets_absolute_quantity(client, auth_headers, product):
    add_resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers
    )
    item_id = add_resp.json()["items"][0]["cart_item_id"]

    resp = client.patch(f"/cart/items/{item_id}", json={"quantity": 7}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["quantity"] == 7


def test_remove_item_deletes_line(client, auth_headers, product):
    add_resp = client.post(
        "/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers
    )
    item_id = add_resp.json()["items"][0]["cart_item_id"]

    resp = client.delete(f"/cart/items/{item_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_cart_is_isolated_per_user(client, product):
    headers_a, _ = register_and_login(client)
    headers_b, _ = register_and_login(client)

    client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 1}, headers=headers_a)

    resp_b = client.get("/cart", headers=headers_b)
    assert resp_b.json()["items"] == []


class TestCartEventEmission:
    def test_add_item_emits_add_to_cart_with_correct_delta(self, client, auth_headers, product, emitted_events):
        client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 3}, headers=auth_headers)

        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "add_to_cart"]
        assert len(matching) == 1
        payload = matching[0]["payload"]
        assert payload["quantity_added"] == 3
        assert payload["cart_quantity_after"] == 3

    def test_second_add_emits_delta_only_not_running_total(self, client, auth_headers, product, emitted_events):
        client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers)
        emitted_events.clear()
        client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 3}, headers=auth_headers)

        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "add_to_cart"]
        assert len(matching) == 1
        assert matching[0]["payload"]["quantity_added"] == 3  # the delta, not 2+3
        assert matching[0]["payload"]["cart_quantity_after"] == 5

    def test_patch_increasing_quantity_emits_add_to_cart(self, client, auth_headers, product, emitted_events):
        add_resp = client.post(
            "/cart/items", json={"product_id": str(product.product_id), "quantity": 2}, headers=auth_headers
        )
        item_id = add_resp.json()["items"][0]["cart_item_id"]
        emitted_events.clear()

        client.patch(f"/cart/items/{item_id}", json={"quantity": 5}, headers=auth_headers)
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "add_to_cart"]
        assert len(matching) == 1
        assert matching[0]["payload"]["quantity_added"] == 3
        assert matching[0]["payload"]["cart_quantity_after"] == 5

    def test_patch_decreasing_quantity_emits_remove_from_cart(self, client, auth_headers, product, emitted_events):
        add_resp = client.post(
            "/cart/items", json={"product_id": str(product.product_id), "quantity": 5}, headers=auth_headers
        )
        item_id = add_resp.json()["items"][0]["cart_item_id"]
        emitted_events.clear()

        client.patch(f"/cart/items/{item_id}", json={"quantity": 2}, headers=auth_headers)
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "remove_from_cart"]
        assert len(matching) == 1
        assert matching[0]["payload"]["quantity_removed"] == 3
        assert matching[0]["payload"]["cart_quantity_after"] == 2

    def test_patch_same_quantity_emits_nothing(self, client, auth_headers, product, emitted_events):
        # §31: delta = 0 -> emit nothing.
        add_resp = client.post(
            "/cart/items", json={"product_id": str(product.product_id), "quantity": 4}, headers=auth_headers
        )
        item_id = add_resp.json()["items"][0]["cart_item_id"]
        emitted_events.clear()

        client.patch(f"/cart/items/{item_id}", json={"quantity": 4}, headers=auth_headers)
        assert emitted_events == []

    def test_delete_item_emits_remove_from_cart_to_zero(self, client, auth_headers, product, emitted_events):
        add_resp = client.post(
            "/cart/items", json={"product_id": str(product.product_id), "quantity": 4}, headers=auth_headers
        )
        item_id = add_resp.json()["items"][0]["cart_item_id"]
        emitted_events.clear()

        client.delete(f"/cart/items/{item_id}", headers=auth_headers)
        matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "remove_from_cart"]
        assert len(matching) == 1
        assert matching[0]["payload"]["quantity_removed"] == 4
        assert matching[0]["payload"]["cart_quantity_after"] == 0

    def test_failed_add_discontinued_product_emits_nothing(self, client, auth_headers, db_session, product, emitted_events):
        product.product_status = "DISCONTINUED"
        db_session.flush()
        emitted_events.clear()  # auth_headers fixture already emitted user_registered/user_login
        client.post("/cart/items", json={"product_id": str(product.product_id), "quantity": 1}, headers=auth_headers)
        assert emitted_events == []
