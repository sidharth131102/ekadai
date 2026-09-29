from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: uuid.UUID
    category_name: str
    category_status: str


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: uuid.UUID
    product_name: str
    category_id: uuid.UUID
    brand: str | None
    base_price: Decimal
    product_status: str
    description: str | None = None
    image_url: str | None = None
    # Computed via aggregate query (app/routers/catalog.py), not stored on the row —
    # never denormalized onto products, same reasoning §16 gives for keeping it lean.
    average_rating: float | None = None
    review_count: int = 0


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


# "rating" was unavailable until Phase 2c added the reviews table — now backed by real
# aggregated data, not fabricated.
ProductSortField = Literal["price", "newest", "popularity", "rating"]
SortOrder = Literal["asc", "desc"]
