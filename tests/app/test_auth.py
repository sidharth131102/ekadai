import uuid

from tests.app.conftest import register_and_login


def test_register_creates_user_and_returns_token(client):
    email = f"{uuid.uuid4()}@example.com"
    resp = client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == email
    assert body["user"]["account_status"] == "ACTIVE"
    assert body["access_token"]


def test_register_duplicate_email_rejected(client):
    email = f"{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    resp = client.post("/auth/register", json={"email": email, "password": "otherpass123"})
    assert resp.status_code == 409


def test_login_success(client):
    email = f"{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    resp = client.post("/auth/login", json={"email": email, "password": "hunter2pass"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password_rejected(client):
    email = f"{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    resp = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/users/me")
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    headers, user = register_and_login(client)
    resp = client.get("/users/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == user["user_id"]


def test_logout_is_no_op_success(client):
    headers, _user = register_and_login(client)
    resp = client.post("/auth/logout", headers=headers)
    assert resp.status_code == 204


def test_register_with_session_header_carries_session_id(client, emitted_events):
    # Phase 3b retrofit: the shared session_id/device dependencies now populate the
    # already-wired Phase 3a server events too, not just the new client-emittable ones.
    email = f"{uuid.uuid4()}@example.com"
    client.post(
        "/auth/register",
        json={"email": email, "password": "hunter2pass"},
        headers={"X-Session-Id": "sess-retrofit-1"},
    )
    matching = [e for e in emitted_events if e["event"]["event_type"] == "user_registered"]
    assert matching[0]["event"]["context"]["session_id"] == "sess-retrofit-1"


def test_register_emits_exactly_one_user_registered_event(client, emitted_events):
    email = f"{uuid.uuid4()}@example.com"
    resp = client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    user_id = resp.json()["user"]["user_id"]

    matching = [e for e in emitted_events if e["event"]["event_type"] == "user_registered"]
    assert len(matching) == 1
    event = matching[0]["event"]
    assert event["context"]["user_id"] == user_id
    assert event["payload"]["registration"]["registration_method"] == "email"
    assert matching[0]["topic"] == "user-events"
    assert matching[0]["key"] == user_id


def test_login_emits_user_login_event(client, emitted_events):
    email = f"{uuid.uuid4()}@example.com"
    client.post("/auth/register", json={"email": email, "password": "hunter2pass"})
    emitted_events.clear()

    client.post("/auth/login", json={"email": email, "password": "hunter2pass"})
    matching = [e for e in emitted_events if e["event"]["event_type"] == "user_login"]
    assert len(matching) == 1


def test_failed_login_emits_no_event(client, emitted_events):
    client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrongpassword"})
    assert emitted_events == []


def test_logout_emits_user_logout_event(client, emitted_events):
    headers, user = register_and_login(client)
    emitted_events.clear()

    client.post("/auth/logout", headers=headers)
    matching = [e for e in emitted_events if e["event"]["event_type"] == "user_logout"]
    assert len(matching) == 1
    assert matching[0]["event"]["context"]["user_id"] == user["user_id"]
