from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_device_info, get_session_id
from app.errors import ConflictError, NotFoundError
from app.schemas.wishlist import WishlistAddRequest, WishlistItemOut, WishlistOut
from db.models import Product, User, Wishlist, WishlistItem
from events.envelope import DeviceInfo, EventContext
from events.producer import get_producer

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


def _get_wishlist(db: Session, user_id: uuid.UUID) -> Wishlist:
    # Created eagerly at registration (app/routers/auth.py) — always exists.
    wishlist = db.execute(select(Wishlist).where(Wishlist.user_id == user_id)).scalar_one_or_none()
    if wishlist is None:
        raise NotFoundError("Wishlist not found")
    return wishlist


def _serialize(db: Session, wishlist: Wishlist) -> WishlistOut:
    rows = db.execute(
        select(WishlistItem, Product)
        .join(Product, Product.product_id == WishlistItem.product_id)
        .where(WishlistItem.wishlist_id == wishlist.wishlist_id)
    ).all()
    items = [
        WishlistItemOut(
            wishlist_item_id=wi.wishlist_item_id,
            product_id=p.product_id,
            product_name=p.product_name,
            product_status=p.product_status,
            base_price=p.base_price,
        )
        for wi, p in rows
    ]
    return WishlistOut(wishlist_id=wishlist.wishlist_id, items=items)


@router.get("", response_model=WishlistOut)
def get_wishlist(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> WishlistOut:
    wishlist = _get_wishlist(db, current_user.user_id)
    return _serialize(db, wishlist)


@router.post("/items", response_model=WishlistOut, status_code=status.HTTP_201_CREATED)
def add_item(
    payload: WishlistAddRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> WishlistOut:
    product = db.get(Product, payload.product_id)
    if product is None:
        raise NotFoundError("Product not found")

    wishlist = _get_wishlist(db, current_user.user_id)
    existing = db.execute(
        select(WishlistItem).where(
            WishlistItem.wishlist_id == wishlist.wishlist_id, WishlistItem.product_id == product.product_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("Product already in wishlist")

    db.add(WishlistItem(wishlist_id=wishlist.wishlist_id, product_id=product.product_id))
    db.commit()
    background_tasks.add_task(
        get_producer().emit,
        "wishlist_added",
        {"wishlist_id": str(wishlist.wishlist_id), "product_id": str(product.product_id)},
        context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
        device=device_info,
    )
    return _serialize(db, wishlist)


@router.delete("/items/{wishlist_item_id}", response_model=WishlistOut)
def remove_item(
    wishlist_item_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    session_id: str | None = Depends(get_session_id),
    device_info: DeviceInfo = Depends(get_device_info),
) -> WishlistOut:
    wishlist = _get_wishlist(db, current_user.user_id)
    item = db.execute(
        select(WishlistItem).where(
            WishlistItem.wishlist_item_id == wishlist_item_id, WishlistItem.wishlist_id == wishlist.wishlist_id
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFoundError("Wishlist item not found")

    product_id = item.product_id
    db.delete(item)
    db.commit()
    background_tasks.add_task(
        get_producer().emit,
        "wishlist_removed",
        {"wishlist_id": str(wishlist.wishlist_id), "product_id": str(product_id)},
        context=EventContext(user_id=str(current_user.user_id), session_id=session_id),
        device=device_info,
    )
    return _serialize(db, wishlist)
