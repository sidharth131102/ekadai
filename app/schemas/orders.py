from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.checkout import BuyNowLine


class OrderCreateRequest(BaseModel):
    checkout_id: uuid.UUID
    address_id: uuid.UUID
    # Must match whatever was passed to POST /checkout/start for this checkout_id (buy-now
    # or cart-sourced) — there's no persisted checkout state to remember it for you (§9).
    buy_now: BuyNowLine | None = None


class OrderItemOut(BaseModel):
    order_item_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    line_revenue: Decimal
    currency: str


class OrderOut(BaseModel):
    order_id: uuid.UUID
    checkout_id: uuid.UUID
    status: str
    total_amount: Decimal
    currency: str
    item_count: int
    total_quantity: int

    shipping_address_line1: str
    shipping_address_line2: str | None
    shipping_city: str
    shipping_state: str
    shipping_postal_code: str
    shipping_country: str

    created_at: datetime
    confirmed_at: datetime
    cancelled_at: datetime | None

    items: list[OrderItemOut]


class OrderSummaryOut(BaseModel):
    order_id: uuid.UUID
    status: str
    total_amount: Decimal
    currency: str
    item_count: int
    total_quantity: int
    created_at: datetime
    cancelled_at: datetime | None


class OrderListResponse(BaseModel):
    items: list[OrderSummaryOut]
    total: int
    page: int
    page_size: int
