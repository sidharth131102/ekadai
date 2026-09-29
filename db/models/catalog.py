"""categories, products (MASTER_BUILD_PROMPT.md §15-§16). Both CDC: YES."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, uuid_pk


class CategoryStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class ProductStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISCONTINUED = "DISCONTINUED"


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    category_id: Mapped[uuid.UUID] = uuid_pk("category_id")
    category_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    category_status: Mapped[CategoryStatus] = mapped_column(
        SAEnum(
            CategoryStatus,
            name="category_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        server_default=CategoryStatus.ACTIVE.value,
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    product_id: Mapped[uuid.UUID] = uuid_pk("product_id")
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: products→categories is explicitly listed in §25 as a table that
        # should resist accidental physical deletion.
        ForeignKey("categories.category_id", ondelete="RESTRICT"),
        nullable=False,
    )
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    # Presentational fields, not covered by §16's conceptual schema — added in Phase 2c in
    # response to direct product feedback. Not business/CDC-semantic, purely additive.
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    product_status: Mapped[ProductStatus] = mapped_column(
        SAEnum(
            ProductStatus,
            name="product_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        server_default=ProductStatus.ACTIVE.value,
    )

    category: Mapped["Category"] = relationship(back_populates="products")

    __table_args__ = (
        CheckConstraint("base_price >= 0", name="base_price_non_negative"),
    )
