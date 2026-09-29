"""users, addresses (MASTER_BUILD_PROMPT.md §13-§14). Both CDC: users=YES, addresses=NO."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum as SAEnum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, uuid_pk


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DEACTIVATED = "DEACTIVATED"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = uuid_pk("user_id")

    # Authentication fields required for login. Never propagated into Kafka/Bronze/Silver/
    # Gold (§13) — only user_id, registration_date, account_status, city, state travel
    # downstream via CDC.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    registration_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_status: Mapped[AccountStatus] = mapped_column(
        SAEnum(
            AccountStatus,
            name="account_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        server_default=AccountStatus.ACTIVE.value,
    )
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)

    addresses: Mapped[list["Address"]] = relationship(back_populates="user")


class Address(Base, TimestampMixin):
    __tablename__ = "addresses"

    address_id: Mapped[uuid.UUID] = uuid_pk("address_id")
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    address_line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(120), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    user: Mapped["User"] = relationship(back_populates="addresses")

    __table_args__ = (
        # "A user may have at most one default address" (§14) — enforced at the DB level
        # via a partial unique index rather than app-level check-then-write.
        Index(
            "uq_addresses_one_default_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_default = true"),
        ),
    )
