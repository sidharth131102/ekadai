from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_device_info, get_session_id
from app.errors import NotFoundError
from app.schemas.orders import (
    OrderCreateRequest,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
    OrderSummaryOut,
)
from app.services.orders import RequestedLine, cancel_order, create_order
from db.models import Order, OrderItem, Product, User
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer

router = APIRouter(prefix="/orders", tags=["orders"])


def _serialize_order(db: Session, order: Order) -> OrderOut:
    rows = db.execute(
        select(OrderItem, Product)
        .join(Product, Product.product_id == OrderItem.product_id)
        .where(OrderItem.order_id == order.order_id)
    ).all()
    items = [
        OrderItemOut(
            order_item_id=oi.order_item_id,
            product_id=p.product_id,
            product_name=p.product_name,
            quantity=oi.quantity,
            unit_price=oi.unit_price,
            discount_amount=oi.discount_amount,
            line_revenue=oi.line_revenue,
            currency=oi.currency,
        )
        for oi, p in rows
    ]
    return OrderOut(
        order_id=order.order_id,
        checkout_id=order.checkout_id,
        status=order.status,
        total_amount=order.total_amount,
        currency=order.currency,
        item_count=order.item_count,
        total_quantity=order.total_quantity,
        shipping_address_line1=order.shipping_address_line1,
        shipping_address_line2=order.shipping_address_line2,
        shipping_city=order.shipping_city,
        shipping_state=order.shipping_state,
        shipping_postal_code=order.shipping_postal_code,
        shipping_country=order.shipping_country,
        created_at=order.created_at,
        confirmed_at=order.confirmed_at,
        cancelled_at=order.cancelled_at,
        items=items,
    )


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    payload: OrderCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> OrderOut:
    buy_now = (
        RequestedLine(product_id=payload.buy_now.product_id, quantity=payload.buy_now.quantity)
        if payload.buy_now
        else None
    )
    order, was_created = create_order(
        db, current_user.user_id, payload.checkout_id, payload.address_id, buy_now=buy_now
    )
    if was_created:
        # Behavioral milestone only (§35) — NOT authoritative for order state, and never
        # re-fired on an idempotent replay of the same checkout_id.
        background_tasks.add_task(
            get_producer().emit,
            "order_created",
            {
                "order_id": str(order.order_id),
                "checkout_id": str(order.checkout_id),
                "item_count": order.item_count,
                "total_quantity": order.total_quantity,
                "order_value": order.total_amount,
            },
            context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
            device=device_info,
        )
    return _serialize_order(db, order)


@router.get("", response_model=OrderListResponse)
def list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OrderListResponse:
    base = select(Order).where(Order.user_id == current_user.user_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    orders = db.execute(
        base.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return OrderListResponse(
        items=[OrderSummaryOut.model_validate(o, from_attributes=True) for o in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrderOut:
    order = db.execute(
        select(Order).where(Order.order_id == order_id, Order.user_id == current_user.user_id)
    ).scalar_one_or_none()
    if order is None:
        raise NotFoundError("Order not found")
    return _serialize_order(db, order)


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order_endpoint(
    order_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> OrderOut:
    # Fired on request receipt, independent of whether cancellation ultimately succeeds
    # (§35: represents the click reaching the system, not the outcome). Emitted
    # synchronously, not via BackgroundTasks: our DomainError exception handler
    # (app/main.py) builds a fresh Response that doesn't carry forward a request's
    # scheduled background tasks, so a task added here would be silently dropped whenever
    # cancel_order() below raises (e.g. cancelling an already-cancelled order) — exactly
    # the case this event needs to survive. get_producer().emit() already can't raise, so
    # calling it inline costs one local write, not request correctness.
    get_producer().emit(
        "order_cancel_clicked",
        {"order_id": str(order_id)},
        context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
        device=device_info,
    )
    order = cancel_order(db, current_user.user_id, order_id)
    return _serialize_order(db, order)
