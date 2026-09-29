"""Exercises the DB-enforced invariants from MASTER_BUILD_PROMPT.md §11-§24 against a live
Postgres instance (db/docker-compose.yml, migrated). Each test writes inside its own
transaction-scoped session and rolls back, so tests don't interfere with each other or with
seeded data.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.config import DATABASE_URL
from db.models import Address, Cart, Category, Order, OrderItem, Product, User

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True)


@pytest.fixture()
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


def make_user(session: Session, **overrides) -> User:
    defaults = dict(
        email=f"{uuid.uuid4()}@example.com",
        password_hash="hashed",
        registration_date=date(2026, 1, 1),
    )
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    session.flush()
    return user


def make_category(session: Session, **overrides) -> Category:
    defaults = dict(category_name=f"cat-{uuid.uuid4()}")
    defaults.update(overrides)
    category = Category(**defaults)
    session.add(category)
    session.flush()
    return category


def make_product(session: Session, category: Category, **overrides) -> Product:
    defaults = dict(
        product_name=f"prod-{uuid.uuid4()}",
        category_id=category.category_id,
        base_price=Decimal("100.00"),
    )
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.flush()
    return product


class TestProductConstraints:
    def test_negative_base_price_rejected(self, session):
        category = make_category(session)
        session.add(
            Product(
                product_name="bad product",
                category_id=category.category_id,
                base_price=Decimal("-1.00"),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    def test_deleting_category_with_products_is_restricted(self, session):
        category = make_category(session)
        make_product(session, category)
        session.delete(category)
        with pytest.raises(IntegrityError):
            session.flush()


class TestCartConstraints:
    def test_duplicate_cart_item_rejected(self, session):
        from db.models import CartItem

        user = make_user(session)
        category = make_category(session)
        product = make_product(session, category)
        cart = Cart(user_id=user.user_id, cart_status="ACTIVE")
        session.add(cart)
        session.flush()

        session.add(CartItem(cart_id=cart.cart_id, product_id=product.product_id, quantity=1))
        session.flush()

        session.add(CartItem(cart_id=cart.cart_id, product_id=product.product_id, quantity=2))
        with pytest.raises(IntegrityError):
            session.flush()

    def test_second_active_cart_for_same_user_rejected(self, session):
        user = make_user(session)
        session.add(Cart(user_id=user.user_id, cart_status="ACTIVE"))
        session.flush()

        session.add(Cart(user_id=user.user_id, cart_status="ACTIVE"))
        with pytest.raises(IntegrityError):
            session.flush()

    def test_second_checked_out_cart_for_same_user_is_allowed(self, session):
        # Only ACTIVE carts are constrained to one-per-user; CHECKED_OUT/ABANDONED carts
        # accumulate as history.
        user = make_user(session)
        session.add(Cart(user_id=user.user_id, cart_status="CHECKED_OUT"))
        session.add(Cart(user_id=user.user_id, cart_status="CHECKED_OUT"))
        session.flush()  # must not raise


class TestAddressConstraints:
    def test_second_default_address_for_same_user_rejected(self, session):
        user = make_user(session)
        session.add(
            Address(
                user_id=user.user_id,
                address_line1="1 Main St",
                city="Metropolis",
                state="NY",
                postal_code="10001",
                country="US",
                is_default=True,
            )
        )
        session.flush()

        session.add(
            Address(
                user_id=user.user_id,
                address_line1="2 Other St",
                city="Metropolis",
                state="NY",
                postal_code="10002",
                country="US",
                is_default=True,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    def test_second_non_default_address_is_allowed(self, session):
        user = make_user(session)
        session.add(
            Address(
                user_id=user.user_id,
                address_line1="1 Main St",
                city="Metropolis",
                state="NY",
                postal_code="10001",
                country="US",
                is_default=False,
            )
        )
        session.add(
            Address(
                user_id=user.user_id,
                address_line1="2 Other St",
                city="Metropolis",
                state="NY",
                postal_code="10002",
                country="US",
                is_default=False,
            )
        )
        session.flush()  # must not raise


class TestOrderItemConstraints:
    def _make_order(self, session: Session) -> Order:
        user = make_user(session)
        order = Order(
            user_id=user.user_id,
            checkout_id=uuid.uuid4(),
            status="CONFIRMED",
            total_amount=Decimal("100.00"),
            currency="USD",
            item_count=1,
            total_quantity=1,
            shipping_address_line1="1 Main St",
            shipping_city="Metropolis",
            shipping_state="NY",
            shipping_postal_code="10001",
            shipping_country="US",
            confirmed_at=datetime.now(timezone.utc),
        )
        session.add(order)
        session.flush()
        return order

    def test_discount_exceeding_gross_value_rejected(self, session):
        order = self._make_order(session)
        category = make_category(session)
        product = make_product(session, category)
        session.add(
            OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=1,
                unit_price=Decimal("10.00"),
                discount_amount=Decimal("11.00"),  # > quantity * unit_price
                line_revenue=Decimal("-1.00"),
                currency="USD",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    def test_line_revenue_must_match_formula(self, session):
        order = self._make_order(session)
        category = make_category(session)
        product = make_product(session, category)
        session.add(
            OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=2,
                unit_price=Decimal("10.00"),
                discount_amount=Decimal("5.00"),
                line_revenue=Decimal("999.00"),  # should be 2*10 - 5 = 15.00
                currency="USD",
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    def test_valid_order_item_is_accepted(self, session):
        order = self._make_order(session)
        category = make_category(session)
        product = make_product(session, category)
        session.add(
            OrderItem(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=2,
                unit_price=Decimal("10.00"),
                discount_amount=Decimal("5.00"),
                line_revenue=Decimal("15.00"),
                currency="USD",
            )
        )
        session.flush()  # must not raise


class TestOrderLifecycleConstraints:
    def test_confirmed_order_with_cancelled_at_set_rejected(self, session):
        user = make_user(session)
        session.add(
            Order(
                user_id=user.user_id,
                checkout_id=uuid.uuid4(),
                status="CONFIRMED",
                total_amount=Decimal("50.00"),
                currency="USD",
                item_count=1,
                total_quantity=1,
                shipping_address_line1="1 Main St",
                shipping_city="Metropolis",
                shipping_state="NY",
                shipping_postal_code="10001",
                shipping_country="US",
                confirmed_at=datetime.now(timezone.utc),
                cancelled_at=datetime.now(timezone.utc),  # invalid for CONFIRMED
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()

    def test_item_count_exceeding_total_quantity_rejected(self, session):
        user = make_user(session)
        session.add(
            Order(
                user_id=user.user_id,
                checkout_id=uuid.uuid4(),
                status="CONFIRMED",
                total_amount=Decimal("50.00"),
                currency="USD",
                item_count=5,
                total_quantity=2,  # item_count > total_quantity, invalid
                shipping_address_line1="1 Main St",
                shipping_city="Metropolis",
                shipping_state="NY",
                shipping_postal_code="10001",
                shipping_country="US",
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
