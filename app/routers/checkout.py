from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, status
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_current_user, get_db, get_device_info, get_session_id
from app.schemas.checkout import CheckoutSnapshotOut, CheckoutStartRequest
from app.services.orders import RequestedLine, build_checkout_snapshot
from db.models import User
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer

router = APIRouter(prefix="/checkout", tags=["checkout"])


@router.post("/start", response_model=CheckoutSnapshotOut, status_code=status.HTTP_201_CREATED)
def start_checkout(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
    payload: CheckoutStartRequest = Body(default=CheckoutStartRequest()),
) -> CheckoutSnapshotOut:
    """Ephemeral snapshot — nothing is persisted (§9: no `checkouts` table). If the cart
    changes before POST /orders is called, order creation recomputes fresh from the live
    cart; `checkout_id` is a pure correlation id, not a pointer to stored state. With
    `buy_now` in the body, prices that single product/quantity instead (§32) — no cart is
    read at all."""
    buy_now = (
        RequestedLine(product_id=payload.buy_now.product_id, quantity=payload.buy_now.quantity)
        if payload.buy_now
        else None
    )
    cart, priced_lines = build_checkout_snapshot(db, current_user.user_id, buy_now=buy_now)

    gross_merchandise_value = sum(
        (line["unit_price"] * line["quantity"] for line in priced_lines), Decimal("0.00")
    )
    discount_amount = sum((line["discount_amount"] for line in priced_lines), Decimal("0.00"))
    cart_net_value = gross_merchandise_value - discount_amount
    checkout_id = uuid.uuid4()
    item_count = len(priced_lines)
    total_quantity = sum(line["quantity"] for line in priced_lines)

    background_tasks.add_task(
        get_producer().emit,
        "checkout_started",
        {
            "checkout_id": str(checkout_id),
            "cart_id": str(cart.cart_id) if cart else None,
            "item_count": item_count,
            "total_quantity": total_quantity,
            "gross_merchandise_value": gross_merchandise_value,
            "discount_amount": discount_amount,
            "cart_net_value": cart_net_value,
            "currency": settings.default_currency,
        },
        context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
        device=device_info,
    )

    return CheckoutSnapshotOut(
        checkout_id=checkout_id,
        cart_id=cart.cart_id if cart else None,
        item_count=item_count,
        total_quantity=total_quantity,
        gross_merchandise_value=gross_merchandise_value,
        discount_amount=discount_amount,
        cart_net_value=cart_net_value,
        currency=settings.default_currency,
    )
