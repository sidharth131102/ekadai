"""Test isolation for the API test suite.

Uses a dedicated Postgres database (settings.test_database_url) so it never touches dev
data, migrated once per test session. Each test runs inside an outer transaction +
SAVEPOINT that's rolled back afterward — the standard SQLAlchemy recipe for letting
application code call session.commit() freely while the test harness still discards
everything at the end (see "Joining a Session into an External Transaction" in the
SQLAlchemy docs).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.config import settings
from app.deps import get_db
from app.main import app
from db.config import DATABASE_URL as DEV_DATABASE_URL
from db.models import Category, Product, Promotion, PromotionTarget
from events import producer as events_producer


def _admin_url() -> str:
    # Connect to the dev DB just to issue CREATE DATABASE for the test DB (can't CREATE
    # DATABASE from within a transaction on the DB being created).
    return DEV_DATABASE_URL


def _ensure_test_database_exists() -> None:
    test_db_name = settings.test_database_url.rsplit("/", 1)[-1]
    engine = create_engine(_admin_url(), future=True, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_db_name}
        ).scalar_one_or_none()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    engine.dispose()


def _run_migrations() -> None:
    env = {**os.environ, "DATABASE_URL": settings.test_database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "db/alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def test_engine():
    _ensure_test_database_exists()
    _run_migrations()
    engine = create_engine(settings.test_database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(test_engine):
    connection = test_engine.connect()
    outer_transaction = connection.begin()
    TestSessionLocal = sessionmaker(bind=connection, future=True)
    session: Session = TestSessionLocal()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, transaction):
        if transaction.nested and not transaction._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


class CapturingTransport:
    """Test-only EventTransport — captures every emitted event in memory instead of
    writing to var/events.log, so tests can assert exactly what was (or wasn't) emitted."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, topic, key, event):
        self.sent.append({"topic": topic, "key": key, "event": event})


@pytest.fixture()
def emitted_events():
    """Autouse-free by design (opt in via the fixture arg) — swaps the producer's transport
    for the duration of the test and restores the real one afterward. BackgroundTasks run
    synchronously within TestClient's request handling, so events are captured before
    client.post()/.patch()/etc. returns."""
    transport = CapturingTransport()
    original = events_producer._producer
    events_producer.set_transport(transport)
    try:
        yield transport.sent
    finally:
        events_producer._producer = original


@pytest.fixture()
def client(db_session, emitted_events):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def category(db_session) -> Category:
    cat = Category(category_name=f"cat-{uuid.uuid4()}", category_status="ACTIVE")
    db_session.add(cat)
    db_session.flush()
    return cat


@pytest.fixture()
def product(db_session, category) -> Product:
    p = Product(
        product_name=f"prod-{uuid.uuid4()}",
        category_id=category.category_id,
        base_price=Decimal("100.00"),
        product_status="ACTIVE",
    )
    db_session.add(p)
    db_session.flush()
    return p


def register_and_login(client: TestClient, email: str | None = None, password: str = "hunter2pass") -> dict:
    email = email or f"{uuid.uuid4()}@example.com"
    resp = client.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, resp.json()["user"]


@pytest.fixture()
def auth_headers(client) -> dict:
    headers, _user = register_and_login(client)
    return headers


def make_sitewide_promotion(
    db_session,
    discount_type: str = "PERCENTAGE",
    discount_value: Decimal = Decimal("10.00"),
    priority: int = 1,
    start_at=None,
    end_at=None,
):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    promo = Promotion(
        promotion_name=f"promo-{uuid.uuid4()}",
        discount_type=discount_type,
        discount_value=discount_value,
        priority=priority,
        start_at=start_at or (now - timedelta(days=1)),
        end_at=end_at,
        promotion_status="ACTIVE",
    )
    db_session.add(promo)
    db_session.flush()
    db_session.add(PromotionTarget(promotion_id=promo.promotion_id, target_type="SITEWIDE"))
    db_session.flush()
    return promo
