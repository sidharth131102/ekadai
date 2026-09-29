from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel


class WishlistItemOut(BaseModel):
    wishlist_item_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_status: str
    base_price: Decimal


class WishlistOut(BaseModel):
    wishlist_id: uuid.UUID
    items: list[WishlistItemOut]


class WishlistAddRequest(BaseModel):
    product_id: uuid.UUID
