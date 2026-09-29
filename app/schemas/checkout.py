from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class BuyNowLine(BaseModel):
    """Present -> price/lock this single product+quantity, bypassing the cart entirely
    (§32). Absent -> ordinary cart-sourced checkout (unchanged)."""

    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class CheckoutStartRequest(BaseModel):
    buy_now: BuyNowLine | None = None


class CheckoutSnapshotOut(BaseModel):
    """Ephemeral — computed from the live cart (or a single buy-now line), never persisted
    (§9: no `checkouts` table)."""

    checkout_id: uuid.UUID
    cart_id: uuid.UUID | None  # None for a buy-now snapshot — no cart is involved
    item_count: int
    total_quantity: int
    gross_merchandise_value: Decimal
    discount_amount: Decimal
    cart_net_value: Decimal
    currency: str
