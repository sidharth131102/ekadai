"""orders, order_items (MASTER_BUILD_PROMPT.md §23-§24). Both CDC: YES — authoritative
for order lifecycle and historical transaction values."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, uuid_pk


class OrderStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    order_id: Mapped[uuid.UUID] = uuid_pk("order_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT: orders→users is explicitly listed in §25 as resisting accidental
        # physical deletion.
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Every order originates from exactly one checkout (§9); unique so a checkout can
    # never accidentally produce multiple orders (§23).
    checkout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(
            OrderStatus,
            name="order_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    total_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    shipping_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    shipping_address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shipping_city: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_state: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_country: Mapped[str] = mapped_column(String(2), nullable=False)

    confirmed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        CheckConstraint("item_count > 0", name="item_count_positive"),
        CheckConstraint("total_quantity > 0", name="total_quantity_positive"),
        CheckConstraint("item_count <= total_quantity", name="item_count_le_total_quantity"),
        # Lifecycle consistency (§23): CONFIRMED => confirmed_at set, cancelled_at null;
        # CANCELLED => both set. No PENDING state exists (§8, §111).
        CheckConstraint(
            "(status = 'CONFIRMED' AND confirmed_at IS NOT NULL AND cancelled_at IS NULL) OR "
            "(status = 'CANCELLED' AND confirmed_at IS NOT NULL AND cancelled_at IS NOT NULL)",
            name="status_lifecycle_consistency",
        ),
        Index("ix_orders_user_id", "user_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_cancelled_at", "cancelled_at"),
    )


class OrderItem(Base, TimestampMixin):
    __tablename__ = "order_items"

    order_item_id: Mapped[uuid.UUID] = uuid_pk("order_item_id")
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.order_id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    discount_amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    line_revenue: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_non_negative"),
        CheckConstraint(
            "discount_amount <= quantity * unit_price", name="discount_le_gross_value"
        ),
        CheckConstraint(
            "line_revenue = (quantity * unit_price) - discount_amount",
            name="line_revenue_matches_formula",
        ),
        UniqueConstraint("order_id", "product_id", name="uq_order_items_order_product"),
    )
