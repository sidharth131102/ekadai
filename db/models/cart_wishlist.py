"""cart, cart_items, wishlist, wishlist_items (MASTER_BUILD_PROMPT.md §19-§22). CDC: NO."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Enum as SAEnum, ForeignKey, Index, Integer, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.models.base import Base, TimestampMixin, uuid_pk


class CartStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CHECKED_OUT = "CHECKED_OUT"
    ABANDONED = "ABANDONED"


class Cart(Base, TimestampMixin):
    __tablename__ = "cart"

    cart_id: Mapped[uuid.UUID] = uuid_pk("cart_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    cart_status: Mapped[CartStatus] = mapped_column(
        SAEnum(
            CartStatus,
            name="cart_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        server_default=CartStatus.ACTIVE.value,
    )

    items: Mapped[list["CartItem"]] = relationship(back_populates="cart")

    __table_args__ = (
        # "At most one ACTIVE cart per user" (§19).
        Index(
            "uq_cart_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("cart_status = 'ACTIVE'"),
        ),
    )


class CartItem(Base, TimestampMixin):
    __tablename__ = "cart_items"

    cart_item_id: Mapped[uuid.UUID] = uuid_pk("cart_item_id")
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cart.cart_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # RESTRICT, not CASCADE: products are never hard-deleted in normal lifecycle
        # (status-based per §25); this just guards against an accidental product
        # delete silently wiping cart contents.
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    cart: Mapped["Cart"] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("cart_id", "product_id", name="uq_cart_items_cart_product"),
    )


class Wishlist(Base, TimestampMixin):
    __tablename__ = "wishlist"

    wishlist_id: Mapped[uuid.UUID] = uuid_pk("wishlist_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    items: Mapped[list["WishlistItem"]] = relationship(back_populates="wishlist")


class WishlistItem(Base):
    __tablename__ = "wishlist_items"

    wishlist_item_id: Mapped[uuid.UUID] = uuid_pk("wishlist_item_id")
    wishlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wishlist.wishlist_id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.product_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # §22 lists only created_at (no updated_at) — wishlist items are add/remove only.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    wishlist: Mapped["Wishlist"] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("wishlist_id", "product_id", name="uq_wishlist_items_wishlist_product"),
    )
