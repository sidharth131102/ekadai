ADDRESS_PAYLOAD = {
    "address_line1": "1 Main St",
    "city": "Metropolis",
    "state": "NY",
    "postal_code": "10001",
    "country": "US",
}


def test_create_address(client, auth_headers):
    resp = client.post("/users/me/addresses", json=ADDRESS_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_default"] is False


def test_second_default_address_unsets_first(client, auth_headers):
    first = client.post(
        "/users/me/addresses", json={**ADDRESS_PAYLOAD, "is_default": True}, headers=auth_headers
    ).json()
    second = client.post(
        "/users/me/addresses",
        json={**ADDRESS_PAYLOAD, "address_line1": "2 Other St", "is_default": True},
        headers=auth_headers,
    ).json()

    listing = client.get("/users/me/addresses", headers=auth_headers).json()
    defaults = [a for a in listing if a["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["address_id"] == second["address_id"]
    assert first["address_id"] != second["address_id"]


def test_delete_address(client, auth_headers):
    created = client.post("/users/me/addresses", json=ADDRESS_PAYLOAD, headers=auth_headers).json()
    resp = client.delete(f"/users/me/addresses/{created['address_id']}", headers=auth_headers)
    assert resp.status_code == 204

    listing = client.get("/users/me/addresses", headers=auth_headers).json()
    assert listing == []


def test_addresses_isolated_per_user(client):
    from tests.app.conftest import register_and_login

    headers_a, _ = register_and_login(client)
    headers_b, _ = register_and_login(client)
    client.post("/users/me/addresses", json=ADDRESS_PAYLOAD, headers=headers_a)

    listing_b = client.get("/users/me/addresses", headers=headers_b).json()
    assert listing_b == []
