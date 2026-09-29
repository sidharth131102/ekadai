"""Idempotently creates a dedicated `debezium` Postgres role (LOGIN + REPLICATION) with
ownership of exactly the 5 CDC tables (§45) — narrower than reusing the connecting admin role,
matching §44's "dedicated" framing in spirit. Debezium creates the publication itself
(`publication.autocreate.mode=filtered`) and the replication slot on first connect, so neither
is created here — but that publication-creation DDL requires both CREATE on the database and
*ownership* of every table being added (confirmed by the connector's first two real run
attempts: "permission denied for database ekadai" without the former, "must be owner of table"
with SELECT-only on the latter — Postgres's publication-membership check is ownership-gated,
not SELECT-gated).

Portable across both a self-hosted superuser (local Postgres) and a managed-Postgres admin role
that ISN'T a true superuser (Supabase's `postgres` role) — confirmed via Supabase itself: its
`ALTER TABLE ... OWNER TO debezium` failed with "must be able to SET ROLE debezium" until the
connecting role was made a member of `debezium` first. Uses `CURRENT_USER`/`CURRENT_DATABASE()`
throughout rather than hardcoding either, so the same script works against both.

Run as `python -m debezium.setup_postgres`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, text

from db.config import DATABASE_URL

CDC_TABLES = ["users", "products", "categories", "orders", "order_items"]
ROLE = "debezium"
PASSWORD = "debezium"


def main() -> None:
    engine = create_engine(DATABASE_URL, future=True, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": ROLE}).scalar()
        if not exists:
            # Dev-only fixed credential (not a secret) — inlined rather than bound, since
            # CREATE ROLE's PASSWORD clause is DDL, not a query parameter slot.
            conn.execute(text(f"CREATE ROLE {ROLE} WITH LOGIN REPLICATION PASSWORD '{PASSWORD}'"))
            print(f"created role {ROLE!r}")
        else:
            print(f"role {ROLE!r} already exists")

        current_user = conn.execute(text("SELECT current_user")).scalar()
        current_db = conn.execute(text("SELECT current_database()")).scalar()

        # Needed before ALTER TABLE ... OWNER TO will work when the connecting role isn't a
        # true superuser (e.g. Supabase's `postgres` role) — it must be able to SET ROLE to the
        # target owner. Harmless no-op when it's already a superuser (local Postgres).
        conn.execute(text(f'GRANT {ROLE} TO "{current_user}"'))

        # Modern Postgres requires the new owner to hold CREATE on the containing schema, not
        # just USAGE, before ALTER TABLE ... OWNER TO will succeed (confirmed via Supabase:
        # USAGE alone still failed with "permission denied for schema public").
        conn.execute(text(f"GRANT USAGE, CREATE ON SCHEMA public TO {ROLE}"))
        # Ownership (not just SELECT) is what Postgres actually requires to add a table to a
        # publication — see module docstring. ALTER TABLE ... OWNER TO is itself idempotent.
        for table in CDC_TABLES:
            conn.execute(text(f"ALTER TABLE public.{table} OWNER TO {ROLE}"))
            # §46: UPDATE/DELETE events must carry the full old row in `before`. Postgres's
            # default replica identity only logs the primary key (UPDATE before = null), which
            # would leave e.g. silver_cdc_orders.status_before always empty. Idempotent.
            conn.execute(text(f"ALTER TABLE public.{table} REPLICA IDENTITY FULL"))
        # Required for Debezium's publication.autocreate.mode=filtered to run its own
        # CREATE PUBLICATION ... FOR TABLE (...) DDL.
        conn.execute(text(f'GRANT CREATE ON DATABASE "{current_db}" TO {ROLE}'))
        print(f"granted USAGE on schema public + ownership of {CDC_TABLES} + CREATE on database to {ROLE!r}")
        print(f"set REPLICA IDENTITY FULL on {CDC_TABLES}")


if __name__ == "__main__":
    main()
