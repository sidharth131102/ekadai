"""reviews (Phase 2c — not in MASTER_BUILD_PROMPT.md's locked §12 table list; added in
response to direct product feedback, with explicit user sign-off on seeding sample content).
CDC: NO — same precedent as cart/wishlist/promotions/addresses, no reason to expand CDC
scope per §12.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, uuid_pk


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"

    review_id: Mapped[uuid.UUID] = uuid_pk("review_id")
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Nullable: seeded/demo reviews aren't tied to a real account — that's the truthful
    # representation (vs. inventing fake user credentials to back them). Real user-submitted
    # reviews always populate this. reviewer_name is always populated either way, snapshotted
    # at submission time — same pattern as orders.shipping_address_* (never a live join back
    # to a mutable source).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_in_range"),
        # A real user may only review a product once; seeded rows (user_id IS NULL) are
        # unconstrained so a product can carry several demo reviews.
        Index(
            "uq_reviews_product_user",
            "product_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )
