from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_device_info, get_session_id
from app.errors import ConflictError, NotFoundError
from app.schemas.cart import CartAddItemRequest, CartItemOut, CartOut, CartUpdateItemRequest
from db.models import Cart, CartItem, Product, User
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer


def _emit_cart_delta(
    background_tasks: BackgroundTasks,
    user_id: uuid.UUID,
    cart_id: uuid.UUID,
    product_id: uuid.UUID,
    delta: int,
    quantity_after: int,
    session_id: str | None,
    device_info: DeviceInfo,
) -> None:
    """§31: quantity_added/quantity_removed are always positive; delta=0 emits nothing;
    only call this after the mutation has actually succeeded."""
    if delta == 0:
        return
    context = EventContext(user_id=str(user_id), session_id=session_id)
    if delta > 0:
        background_tasks.add_task(
            get_producer().emit,
            "add_to_cart",
            {
                "cart_id": str(cart_id),
                "product_id": str(product_id),
                "quantity_added": delta,
                "cart_quantity_after": quantity_after,
            },
            context=context,
            device=device_info,
        )
    else:
        background_tasks.add_task(
            get_producer().emit,
            "remove_from_cart",
            {
                "cart_id": str(cart_id),
                "product_id": str(product_id),
                "quantity_removed": abs(delta),
                "cart_quantity_after": quantity_after,
            },
            context=context,
            device=device_info,
        )

router = APIRouter(prefix="/cart", tags=["cart"])


def _serialize_cart(db: Session, cart: Cart | None) -> CartOut:
    if cart is None:
        return CartOut(cart_id=None, items=[], item_count=0, total_quantity=0)

    rows = db.execute(
        select(CartItem, Product).join(Product, Product.product_id == CartItem.product_id).where(CartItem.cart_id == cart.cart_id)
    ).all()
    items = [
        CartItemOut(
            cart_item_id=ci.cart_item_id,
            product_id=p.product_id,
            product_name=p.product_name,
            product_status=p.product_status,
            quantity=ci.quantity,
            unit_price=p.base_price,
            line_subtotal=p.base_price * ci.quantity,
        )
        for ci, p in rows
    ]
    return CartOut(
        cart_id=cart.cart_id,
        items=items,
        item_count=len(items),
        total_quantity=sum(i.quantity for i in items),
    )


def _get_active_cart(db: Session, user_id: uuid.UUID) -> Cart | None:
    return db.execute(select(Cart).where(Cart.user_id == user_id, Cart.cart_status == "ACTIVE")).scalar_one_or_none()


@router.get("", response_model=CartOut)
def get_cart(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CartOut:
    cart = _get_active_cart(db, current_user.user_id)
    return _serialize_cart(db, cart)


@router.post("/items", response_model=CartOut, status_code=status.HTTP_201_CREATED)
def add_item(
    payload: CartAddItemRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> CartOut:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise NotFoundError("Product not found")
    if product.product_status != "ACTIVE":
        raise ConflictError("Product is not available")

    cart = _get_active_cart(db, current_user.user_id)
    if cart is None:
        cart = Cart(user_id=current_user.user_id, cart_status="ACTIVE")
        db.add(cart)
        db.flush()

    existing_item = db.execute(
        select(CartItem).where(CartItem.cart_id == cart.cart_id, CartItem.product_id == product.product_id)
    ).scalar_one_or_none()
    if existing_item is not None:
        # add_to_cart semantics (§31): quantity_added is a positive delta on top of
        # whatever is already in the cart, not a replacement.
        existing_item.quantity += payload.quantity
        quantity_after = existing_item.quantity
    else:
        db.add(CartItem(cart_id=cart.cart_id, product_id=product.product_id, quantity=payload.quantity))
        quantity_after = payload.quantity

    db.commit()
    # Only emit after the mutation succeeds (§31).
    _emit_cart_delta(
        background_tasks,
        current_user.user_id,
        cart.cart_id,
        product.product_id,
        payload.quantity,
        quantity_after,
        session_id,
        device_info,
    )
    cart = _get_active_cart(db, current_user.user_id)
    return _serialize_cart(db, cart)


@router.patch("/items/{cart_item_id}", response_model=CartOut)
def update_item(
    cart_item_id: uuid.UUID,
    payload: CartUpdateItemRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> CartOut:
    cart = _get_active_cart(db, current_user.user_id)
    if cart is None:
        raise NotFoundError("Cart item not found")

    item = db.execute(
        select(CartItem).where(CartItem.cart_item_id == cart_item_id, CartItem.cart_id == cart.cart_id)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Cart item not found")

    # Sets an absolute quantity; use DELETE for full removal (cart_quantity_after = 0).
    old_quantity = item.quantity
    item.quantity = payload.quantity
    db.commit()
    _emit_cart_delta(
        background_tasks,
        current_user.user_id,
        cart.cart_id,
        item.product_id,
        payload.quantity - old_quantity,
        payload.quantity,
        session_id,
        device_info,
    )
    cart = _get_active_cart(db, current_user.user_id)
    return _serialize_cart(db, cart)


@router.delete("/items/{cart_item_id}", response_model=CartOut)
def remove_item(
    cart_item_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> CartOut:
    cart = _get_active_cart(db, current_user.user_id)
    if cart is None:
        raise NotFoundError("Cart item not found")

    item = db.execute(
        select(CartItem).where(CartItem.cart_item_id == cart_item_id, CartItem.cart_id == cart.cart_id)
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Cart item not found")

    old_quantity = item.quantity
    product_id = item.product_id
    db.delete(item)
    db.commit()
    _emit_cart_delta(
        background_tasks, current_user.user_id, cart.cart_id, product_id, -old_quantity, 0, session_id, device_info
    )
    cart = _get_active_cart(db, current_user.user_id)
    return _serialize_cart(db, cart)
