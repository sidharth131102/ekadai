"""Engine/session factory for the running app (distinct from tests, which override
`get_db` to bind to a per-test transaction — see tests/app/conftest.py)."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# pool_pre_ping: the database is Supabase's pooler, which closes idle connections server-side.
# Without a liveness check the pool hands that dead connection to the next request, which
# 500s ("server closed the connection unexpectedly"). pool_recycle retires connections before
# the pooler's idle cutoff as a second line of defense.
engine = create_engine(settings.database_url, future=True, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
