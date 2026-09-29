"""The order-creation transaction (§26). See the Phase 2a plan's "Checkout /
order-creation transaction" section for the full design rationale.

Phase 2c adds Buy Now (§32): a genuine bypass of the cart, not a shortcut through it — if
Buy Now added-to-cart-then-checked-out, a user with existing cart items would have those
items swept into the "buy now" order too, breaking the feature's actual promise (buy *this
one item*, right now, independent of the cart). `RequestedLine` is the shared line-item
representation both sources (cart rows, or a single buy_now product+quantity pair) produce,
so pricing/locking/write logic downstream is identical regardless of source; only "where do
the lines come from, and is there a cart to lock/mark CHECKED_OUT" branches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import ConflictError, InternalInvariantError, NotFoundError, UnprocessableError
from app.services.promotions import compute_discount, find_eligible_candidates, resolve_best_promotion
from db.models import Address, Cart, CartItem, Order, OrderItem, Product


@dataclass(frozen=True)
class RequestedLine:
    product_id: uuid.UUID
    quantity: int


def _find_order_by_checkout_id(session: Session, checkout_id: uuid.UUID) -> Order | None:
    return session.execute(select(Order).where(Order.checkout_id == checkout_id)).scalar_one_or_none()


def _price_lines(session: Session, requested_lines: list[RequestedLine], now: datetime) -> list[dict]:
    """Shared pricing step (promotion resolution + discount formula) — an unlocked read,
    source-agnostic. Locking (where atomicity actually matters) happens separately in
    create_order, only for the lines that will actually be written."""
    product_ids = [rl.product_id for rl in requested_lines]
    products = {
        p.product_id: p
        for p in session.execute(select(Product).where(Product.product_id.in_(product_ids))).scalars()
    }
    category_ids = list({products[pid].category_id for pid in product_ids if pid in products})
    candidates = find_eligible_candidates(session, product_ids, category_ids, now)

    priced_lines = []
    for rl in requested_lines:
        product = products.get(rl.product_id)
        if product is None:
            # For buy-now this can't happen (build_checkout_snapshot already checked the
            # product exists before calling here); for cart mode, a cart line referencing a
            # missing product would only be possible via a data-integrity failure (RESTRICT
            # FK should prevent it) — an internal invariant violation either way, not a
            # plain "not found" client error.
            raise InternalInvariantError(f"product {rl.product_id} referenced but missing")
        unit_price = product.base_price
        promo = resolve_best_promotion(candidates, product.product_id, product.category_id)
        discount_amount, line_revenue = compute_discount(unit_price, rl.quantity, promo)
        priced_lines.append(
            {
                "product_id": product.product_id,
                "product_status": product.product_status,
                "quantity": rl.quantity,
                "unit_price": unit_price,
                "discount_amount": discount_amount,
                "line_revenue": line_revenue,
            }
        )
    return priced_lines


def build_checkout_snapshot(
    session: Session, user_id: uuid.UUID, buy_now: RequestedLine | None = None
) -> tuple[Cart | None, list[dict]]:
    """Shared by POST /checkout/start and order creation. Cart mode locates the user's
    ACTIVE cart (unlocked read — only order creation needs the lock); buy-now mode prices a
    single product/quantity pair and never touches the cart at all. Returns (cart, priced
    lines) — cart is None in buy-now mode. Raises UnprocessableError if the cart is
    empty/missing, NotFoundError if the buy-now product doesn't exist.
    """
    now = datetime.now(timezone.utc)

    if buy_now is not None:
        product = session.get(Product, buy_now.product_id)
        if product is None:
            raise NotFoundError("Product not found")
        return None, _price_lines(session, [buy_now], now)

    cart = session.execute(
        select(Cart).where(Cart.user_id == user_id, Cart.cart_status == "ACTIVE")
    ).scalar_one_or_none()
    if cart is None:
        raise UnprocessableError("No active cart to check out")

    cart_items = session.execute(select(CartItem).where(CartItem.cart_id == cart.cart_id)).scalars().all()
    if not cart_items:
        raise UnprocessableError("Cart is empty")

    requested_lines = [RequestedLine(ci.product_id, ci.quantity) for ci in cart_items]
    return cart, _price_lines(session, requested_lines, now)


def create_order(
    session: Session,
    user_id: uuid.UUID,
    checkout_id: uuid.UUID,
    address_id: uuid.UUID,
    buy_now: RequestedLine | None = None,
) -> tuple[Order, bool]:
    """Returns (order, was_created) — was_created is False on an idempotent replay (same
    checkout_id resubmitted), so callers (the order_created event, specifically) only fire
    once per real order, never on a replay."""
    now = datetime.now(timezone.utc)

    # 1. Idempotency fast-path.
    existing = _find_order_by_checkout_id(session, checkout_id)
    if existing is not None:
        return existing, False

    # 2. Locate the lines to charge. Buy-now: no cart involved at all, so an in-progress
    # buy-now purchase can never interact with, block on, or be affected by the user's
    # existing cart. Cart mode: lock the cart row; empty result -> re-check idempotency ->
    # still empty -> conflict (unchanged from before Phase 2c).
    cart: Cart | None = None
    if buy_now is not None:
        requested_lines = [buy_now]
    else:
        cart = session.execute(
            select(Cart).where(Cart.user_id == user_id, Cart.cart_status == "ACTIVE").with_for_update()
        ).scalar_one_or_none()
        if cart is None:
            existing = _find_order_by_checkout_id(session, checkout_id)
            if existing is not None:
                return existing, False
            raise ConflictError("No active cart to check out")

        cart_items = session.execute(select(CartItem).where(CartItem.cart_id == cart.cart_id)).scalars().all()
        if not cart_items:
            raise UnprocessableError("Cart is empty")
        requested_lines = [RequestedLine(ci.product_id, ci.quantity) for ci in cart_items]

    # 3. Lock each referenced product individually, in ascending product_id order
    # (deadlock-safe — see plan for why a batched multi-row lock isn't). Identical for
    # both sources.
    product_ids = sorted({rl.product_id for rl in requested_lines})
    locked_products: dict[uuid.UUID, Product] = {}
    for pid in product_ids:
        product = session.execute(
            select(Product).where(Product.product_id == pid).with_for_update(read=True)
        ).scalar_one_or_none()
        if product is None:
            raise InternalInvariantError(f"product {pid} referenced but missing")
        locked_products[pid] = product

    for rl in requested_lines:
        if locked_products[rl.product_id].product_status != "ACTIVE":
            raise ConflictError(f"product {rl.product_id} is no longer available")

    # 4. Validate address.
    address = session.execute(
        select(Address).where(Address.address_id == address_id, Address.user_id == user_id)
    ).scalar_one_or_none()
    if address is None:
        raise NotFoundError("Address not found")

    # 5-6. Promotion resolution + discount formula, per line.
    category_ids = list({p.category_id for p in locked_products.values()})
    candidates = find_eligible_candidates(session, product_ids, category_ids, now)

    order_items_data: list[dict] = []
    total_amount = Decimal("0.00")
    for rl in requested_lines:
        product = locked_products[rl.product_id]
        unit_price = product.base_price
        promo = resolve_best_promotion(candidates, product.product_id, product.category_id)
        discount_amount, line_revenue = compute_discount(unit_price, rl.quantity, promo)
        order_items_data.append(
            {
                "product_id": product.product_id,
                "quantity": rl.quantity,
                "unit_price": unit_price,
                "discount_amount": discount_amount,
                "line_revenue": line_revenue,
                "currency": settings.default_currency,
            }
        )
        total_amount += line_revenue

    # 7-8. Order-level totals.
    item_count = len(order_items_data)
    total_quantity = sum(item["quantity"] for item in order_items_data)

    # 9. Write phase — one transaction.
    order = Order(
        user_id=user_id,
        checkout_id=checkout_id,
        status="CONFIRMED",
        total_amount=total_amount,
        currency=settings.default_currency,
        item_count=item_count,
        total_quantity=total_quantity,
        shipping_address_line1=address.address_line1,
        shipping_address_line2=address.address_line2,
        shipping_city=address.city,
        shipping_state=address.state,
        shipping_postal_code=address.postal_code,
        shipping_country=address.country,
        created_at=now,
        confirmed_at=now,
        cancelled_at=None,
    )
    session.add(order)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        existing = _find_order_by_checkout_id(session, checkout_id)
        if existing is not None:
            return existing, False
        raise

    for item_data in order_items_data:
        session.add(OrderItem(order_id=order.order_id, **item_data))

    if cart is not None:
        cart.cart_status = "CHECKED_OUT"

    session.commit()
    session.refresh(order)
    return order, True


def cancel_order(session: Session, user_id: uuid.UUID, order_id: uuid.UUID) -> Order:
    """§27: authenticate (caller's job) -> verify ownership -> verify CONFIRMED -> update."""
    order = session.execute(
        select(Order).where(Order.order_id == order_id, Order.user_id == user_id)
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Order not found")
    if order.status != "CONFIRMED":
        raise ConflictError("Only a CONFIRMED order can be cancelled")

    order.status = "CANCELLED"
    order.cancelled_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(order)
    return order
