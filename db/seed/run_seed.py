"""Seed categories + products from db/seed/data/*.json.

Idempotent by name: existing categories/products (matched by name) are left untouched,
new ones are inserted. Safe to re-run.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent
REPO_ROOT = SEED_DIR.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.config import DATABASE_URL
from db.models import Category, Product, Review
from db.seed.review_generator import generate_reviews_for_product


def load_json(name: str) -> list[dict]:
    with open(SEED_DIR / "data" / name, encoding="utf-8") as f:
        return json.load(f)


def seed_categories(session: Session) -> dict[str, Category]:
    existing = {c.category_name: c for c in session.query(Category).all()}
    inserted = 0
    for row in load_json("categories.json"):
        if row["category_name"] in existing:
            continue
        category = Category(
            category_name=row["category_name"],
            category_status=row["category_status"],
        )
        session.add(category)
        existing[row["category_name"]] = category
        inserted += 1
    session.flush()
    print(f"categories: {inserted} inserted, {len(existing) - inserted} already present")
    return existing


def seed_products(session: Session, categories_by_name: dict[str, Category]) -> dict[str, Product]:
    existing = {p.product_name: p for p in session.query(Product).all()}
    inserted = 0
    backfilled = 0
    for row in load_json("products.json"):
        category = categories_by_name.get(row["category_name"])
        if category is None:
            raise ValueError(
                f"product {row['product_name']!r} references unknown category "
                f"{row['category_name']!r}"
            )

        existing_product = existing.get(row["product_name"])
        if existing_product is not None:
            # Phase 2c added description/image_url after the initial seed — backfill them
            # onto already-seeded rows rather than skipping entirely. base_price/status are
            # intentionally left alone (not re-synced) once a product exists.
            if existing_product.description is None and existing_product.image_url is None:
                existing_product.description = row.get("description")
                existing_product.image_url = row.get("image_url")
                backfilled += 1
            continue

        product = Product(
            product_name=row["product_name"],
            category_id=category.category_id,
            brand=row.get("brand"),
            base_price=Decimal(row["base_price"]),
            product_status=row["product_status"],
            description=row.get("description"),
            image_url=row.get("image_url"),
        )
        session.add(product)
        existing[row["product_name"]] = product
        inserted += 1
    session.flush()
    print(f"products: {inserted} inserted, {backfilled} backfilled, {len(existing) - inserted} already present")
    return existing


def seed_reviews(session: Session, products_by_name: dict[str, Product]) -> None:
    existing_product_ids_with_reviews = {
        row[0] for row in session.query(Review.product_id).filter(Review.user_id.is_(None)).distinct()
    }
    inserted = 0
    for product in products_by_name.values():
        if product.product_id in existing_product_ids_with_reviews:
            continue
        for review in generate_reviews_for_product(product.product_name):
            session.add(
                Review(
                    product_id=product.product_id,
                    user_id=None,
                    reviewer_name=review["reviewer_name"],
                    rating=review["rating"],
                    review_text=review["review_text"],
                )
            )
            inserted += 1
    session.flush()
    print(f"reviews: {inserted} inserted")


def main() -> None:
    engine = create_engine(DATABASE_URL, future=True)
    with Session(engine) as session:
        categories_by_name = seed_categories(session)
        products_by_name = seed_products(session, categories_by_name)
        seed_reviews(session, products_by_name)
        session.commit()


if __name__ == "__main__":
    main()
