from tests.app.conftest import register_and_login


def test_list_reviews_empty_for_new_product(client, product):
    resp = client.get(f"/products/{product.product_id}/reviews")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "average_rating": None}


def test_submit_review_and_list_it(client, auth_headers, product):
    resp = client.post(
        f"/products/{product.product_id}/reviews",
        json={"reviewer_name": "Test Buyer", "rating": 4, "review_text": "Pretty good."},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["rating"] == 4
    assert body["is_own"] is True

    listing = client.get(f"/products/{product.product_id}/reviews").json()
    assert listing["total"] == 1
    assert listing["average_rating"] == 4.0
    assert listing["items"][0]["reviewer_name"] == "Test Buyer"
    assert listing["items"][0]["is_own"] is False  # anonymous GET, no auth header


def test_submit_review_requires_auth(client, product):
    resp = client.post(
        f"/products/{product.product_id}/reviews",
        json={"reviewer_name": "Anon", "rating": 5, "review_text": None},
    )
    assert resp.status_code == 401


def test_duplicate_review_by_same_user_rejected(client, auth_headers, product):
    payload = {"reviewer_name": "Repeat Buyer", "rating": 5, "review_text": "Great!"}
    first = client.post(f"/products/{product.product_id}/reviews", json=payload, headers=auth_headers)
    assert first.status_code == 201

    second = client.post(f"/products/{product.product_id}/reviews", json=payload, headers=auth_headers)
    assert second.status_code == 409


def test_two_different_users_can_both_review_same_product(client, product):
    headers_a, _ = register_and_login(client)
    headers_b, _ = register_and_login(client)
    payload_a = {"reviewer_name": "Buyer A", "rating": 5, "review_text": None}
    payload_b = {"reviewer_name": "Buyer B", "rating": 2, "review_text": "Not great."}

    resp_a = client.post(f"/products/{product.product_id}/reviews", json=payload_a, headers=headers_a)
    resp_b = client.post(f"/products/{product.product_id}/reviews", json=payload_b, headers=headers_b)
    assert resp_a.status_code == 201
    assert resp_b.status_code == 201

    listing = client.get(f"/products/{product.product_id}/reviews").json()
    assert listing["total"] == 2
    assert listing["average_rating"] == 3.5


def test_review_on_unknown_product_rejected(client, auth_headers):
    import uuid

    resp = client.post(
        f"/products/{uuid.uuid4()}/reviews",
        json={"reviewer_name": "X", "rating": 3, "review_text": None},
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_invalid_rating_rejected(client, auth_headers, product):
    resp = client.post(
        f"/products/{product.product_id}/reviews",
        json={"reviewer_name": "X", "rating": 7, "review_text": None},
        headers=auth_headers,
    )
    assert resp.status_code == 422
