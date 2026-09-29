"""Shared declarative base, naming convention, and common column helpers.

These SQLAlchemy models are the source of truth for the schema (MASTER_BUILD_PROMPT.md
§11-§24); Alembic migrations are generated from them, not hand-written independently.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import MetaData, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

# Explicit naming convention so every constraint/index gets a deterministic name —
# required for Alembic autogenerate to produce stable, diffable migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk(name: str) -> Mapped[uuid.UUID]:
    """UUID primary key column with a spec-mandated column name, server-generated."""
    return mapped_column(
        name,
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """`created_at` / `updated_at`, TIMESTAMPTZ, UTC. `updated_at` is kept current by a
    DB trigger (`set_updated_at()`, attached per-table in the migration), not app code.
    """

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
