from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class CartItemOut(BaseModel):
    cart_item_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_status: str
    quantity: int
    unit_price: Decimal
    line_subtotal: Decimal


class CartOut(BaseModel):
    cart_id: uuid.UUID | None
    items: list[CartItemOut]
    item_count: int
    total_quantity: int


class CartAddItemRequest(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class CartUpdateItemRequest(BaseModel):
    quantity: int = Field(gt=0)
