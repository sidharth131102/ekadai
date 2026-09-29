"""Environment/config loading shared by Alembic, the seed script, and (later) the app."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://ekadai:ekadai@localhost:5432/ekadai"
)
