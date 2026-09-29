def test_wishlist_exists_immediately_after_registration(client, auth_headers):
    resp = client.get("/wishlist", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_add_and_remove_wishlist_item(client, auth_headers, product):
    add_resp = client.post(
        "/wishlist/items", json={"product_id": str(product.product_id)}, headers=auth_headers
    )
    assert add_resp.status_code == 201
    body = add_resp.json()
    assert len(body["items"]) == 1
    item_id = body["items"][0]["wishlist_item_id"]

    remove_resp = client.delete(f"/wishlist/items/{item_id}", headers=auth_headers)
    assert remove_resp.status_code == 200
    assert remove_resp.json()["items"] == []


def test_add_duplicate_wishlist_item_rejected(client, auth_headers, product):
    client.post("/wishlist/items", json={"product_id": str(product.product_id)}, headers=auth_headers)
    resp = client.post("/wishlist/items", json={"product_id": str(product.product_id)}, headers=auth_headers)
    assert resp.status_code == 409


def test_add_emits_wishlist_added_keyed_by_user(client, auth_headers, product, emitted_events):
    client.post("/wishlist/items", json={"product_id": str(product.product_id)}, headers=auth_headers)
    user_id = client.get("/users/me", headers=auth_headers).json()["user_id"]

    matching = [e for e in emitted_events if e["event"]["event_type"] == "wishlist_added"]
    assert len(matching) == 1
    assert matching[0]["key"] == user_id
    assert matching[0]["event"]["payload"]["product_id"] == str(product.product_id)


def test_remove_emits_wishlist_removed(client, auth_headers, product, emitted_events):
    add_resp = client.post("/wishlist/items", json={"product_id": str(product.product_id)}, headers=auth_headers)
    item_id = add_resp.json()["items"][0]["wishlist_item_id"]
    emitted_events.clear()

    client.delete(f"/wishlist/items/{item_id}", headers=auth_headers)
    matching = [e["event"] for e in emitted_events if e["event"]["event_type"] == "wishlist_removed"]
    assert len(matching) == 1
    assert matching[0]["payload"]["product_id"] == str(product.product_id)
