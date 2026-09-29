from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: uuid.UUID
    reviewer_name: str
    rating: int
    review_text: str | None
    created_at: datetime
    is_own: bool = False


class ReviewListResponse(BaseModel):
    items: list[ReviewOut]
    total: int
    average_rating: float | None


class ReviewCreateRequest(BaseModel):
    # users carries no display-name field (§13 keeps it deliberately minimal) — the
    # submitter provides one, snapshotted onto the review at write time, same pattern as
    # orders.shipping_address_* (never a live join back to a mutable source).
    reviewer_name: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    review_text: str | None = Field(default=None, max_length=4000)
