"""Syncs `image_url` from db/seed/data/products.json onto already-seeded product rows,
matched by product_name.

Unlike `run_seed.py`'s backfill-only-if-empty semantics (which deliberately never overwrites an
already-set image_url/description, to avoid clobbering a live edit), this is an explicit,
repeatable sync step for the actual Phase 2c workflow: images get generated in batches (one
category at a time), `products.json` gets updated with the new local paths, and this script
pushes just that change onto the DB without touching anything else. Safe to re-run — a no-op
for any product whose image_url already matches.

Run as `python -m db.seed.sync_images`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
REPO_ROOT = SEED_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.config import DATABASE_URL
from db.models import Product


def main() -> None:
    with open(SEED_DIR / "data" / "products.json", encoding="utf-8") as f:
        rows = json.load(f)

    engine = create_engine(DATABASE_URL, future=True)
    with Session(engine) as session:
        existing = {p.product_name: p for p in session.query(Product).all()}
        updated = 0
        missing = []
        for row in rows:
            product = existing.get(row["product_name"])
            if product is None:
                missing.append(row["product_name"])
                continue
            new_url = row.get("image_url")
            if new_url and product.image_url != new_url:
                product.image_url = new_url
                updated += 1
        session.commit()

    print(f"image_url synced: {updated} updated, {len(rows) - updated - len(missing)} already up to date")
    if missing:
        print(f"WARNING: {len(missing)} product(s) in products.json not found in DB: {missing}")


if __name__ == "__main__":
    main()
