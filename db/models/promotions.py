"""promotions, promotion_targets (MASTER_BUILD_PROMPT.md §17-§18). Both CDC: NO."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.models.base import Base, TimestampMixin, uuid_pk


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class PromotionTargetType(str, enum.Enum):
    PRODUCT = "PRODUCT"
    CATEGORY = "CATEGORY"
    SITEWIDE = "SITEWIDE"


class Promotion(Base, TimestampMixin):
    __tablename__ = "promotions"

    promotion_id: Mapped[uuid.UUID] = uuid_pk("promotion_id")
    promotion_name: Mapped[str] = mapped_column(String(255), nullable=False)
    discount_type: Mapped[DiscountType] = mapped_column(
        SAEnum(
            DiscountType,
            name="discount_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    discount_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    start_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # Spec (§17) does not enumerate a locked set of allowed values for promotion_status
    # (unlike account/product/category/order status) — left as free-form VARCHAR rather
    # than inventing a business rule the spec didn't lock.
    promotion_status: Mapped[str] = mapped_column(String(30), nullable=False)

    targets: Mapped[list["PromotionTarget"]] = relationship(back_populates="promotion")

    __table_args__ = (
        CheckConstraint("discount_value >= 0", name="discount_value_non_negative"),
    )


class PromotionTarget(Base):
    __tablename__ = "promotion_targets"

    promotion_target_id: Mapped[uuid.UUID] = uuid_pk("promotion_target_id")
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("promotions.promotion_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[PromotionTargetType] = mapped_column(
        SAEnum(
            PromotionTargetType,
            name="promotion_target_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.category_id", ondelete="RESTRICT"),
        nullable=True,
    )
    # §18 lists only created_at for this table (no updated_at) — targets are immutable
    # rows, not TimestampMixin.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    promotion: Mapped["Promotion"] = relationship(back_populates="targets")

    __table_args__ = (
        # Target semantics (§18): PRODUCT -> product_id set, category_id null;
        # CATEGORY -> category_id set, product_id null; SITEWIDE -> both null.
        CheckConstraint(
            "(target_type = 'PRODUCT' AND product_id IS NOT NULL AND category_id IS NULL) OR "
            "(target_type = 'CATEGORY' AND category_id IS NOT NULL AND product_id IS NULL) OR "
            "(target_type = 'SITEWIDE' AND product_id IS NULL AND category_id IS NULL)",
            name="target_type_matches_populated_reference",
        ),
        # "Prevent duplicate targets" (§18) — one partial unique index per target shape,
        # since a plain UNIQUE over nullable columns would not catch duplicate SITEWIDE
        # rows (NULL <> NULL).
        Index(
            "uq_promotion_targets_product",
            "promotion_id",
            "product_id",
            unique=True,
            postgresql_where=text("target_type = 'PRODUCT'"),
        ),
        Index(
            "uq_promotion_targets_category",
            "promotion_id",
            "category_id",
            unique=True,
            postgresql_where=text("target_type = 'CATEGORY'"),
        ),
        Index(
            "uq_promotion_targets_sitewide",
            "promotion_id",
            unique=True,
            postgresql_where=text("target_type = 'SITEWIDE'"),
        ),
    )
