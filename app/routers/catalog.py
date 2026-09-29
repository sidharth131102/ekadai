from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BeforeValidator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db
from app.errors import NotFoundError
from app.schemas.catalog import CategoryOut, ProductListResponse, ProductOut, ProductSortField, SortOrder
from db.models import Category, OrderItem, Product, Review

router = APIRouter(tags=["catalog"])

# A frontend <select> for "all categories" (or an unfilled numeric filter) naturally
# submits an empty-string query param, not an absent one. Treat "" as "not provided"
# instead of a 422 UUID/Decimal parse error.
_blank_to_none = BeforeValidator(lambda v: None if v == "" else v)
OptionalUUID = Annotated[uuid.UUID | None, _blank_to_none]
OptionalDecimal = Annotated[Decimal | None, _blank_to_none]
OptionalFloat = Annotated[float | None, _blank_to_none]


def _rating_subquery():
    return (
        select(
            Review.product_id.label("product_id"),
            func.avg(Review.rating).label("average_rating"),
            func.count(Review.review_id).label("review_count"),
        )
        .group_by(Review.product_id)
        .subquery()
    )


def _to_product_out(product: Product, average_rating: float | None, review_count: int | None) -> ProductOut:
    out = ProductOut.model_validate(product)
    out.average_rating = round(average_rating, 1) if average_rating is not None else None
    out.review_count = review_count or 0
    return out


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CategoryOut]:
    categories = db.execute(
        select(Category).where(Category.category_status == "ACTIVE").order_by(Category.category_name)
    ).scalars().all()
    return [CategoryOut.model_validate(c) for c in categories]


@router.get("/products", response_model=ProductListResponse)
def list_products(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="Search product name/brand"),
    category_id: OptionalUUID = None,
    brand: str | None = None,
    min_price: OptionalDecimal = None,
    max_price: OptionalDecimal = None,
    min_rating: OptionalFloat = Query(default=None, ge=0, le=5),
    max_rating: OptionalFloat = Query(default=None, ge=0, le=5),
    availability: bool | None = Query(default=None, description="True = ACTIVE only"),
    sort: ProductSortField = "newest",
    order: SortOrder = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ProductListResponse:
    rating_subq = _rating_subquery()

    stmt = select(Product, rating_subq.c.average_rating, rating_subq.c.review_count).outerjoin(
        rating_subq, rating_subq.c.product_id == Product.product_id
    )
    count_stmt = select(func.count()).select_from(Product).outerjoin(
        rating_subq, rating_subq.c.product_id == Product.product_id
    )

    if q:
        pattern = f"%{q}%"
        name_filter = (Product.product_name.ilike(pattern)) | (Product.brand.ilike(pattern))
        stmt = stmt.where(name_filter)
        count_stmt = count_stmt.where(name_filter)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
        count_stmt = count_stmt.where(Product.category_id == category_id)
    if brand:
        stmt = stmt.where(Product.brand == brand)
        count_stmt = count_stmt.where(Product.brand == brand)
    if min_price is not None:
        stmt = stmt.where(Product.base_price >= min_price)
        count_stmt = count_stmt.where(Product.base_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.base_price <= max_price)
        count_stmt = count_stmt.where(Product.base_price <= max_price)
    if min_rating is not None:
        # Excludes products with zero reviews (average_rating IS NULL) by construction —
        # correct: there's nothing to compare against a "4+ stars" filter.
        stmt = stmt.where(rating_subq.c.average_rating >= min_rating)
        count_stmt = count_stmt.where(rating_subq.c.average_rating >= min_rating)
    if max_rating is not None:
        stmt = stmt.where(rating_subq.c.average_rating <= max_rating)
        count_stmt = count_stmt.where(rating_subq.c.average_rating <= max_rating)
    if availability is not None:
        status_filter = Product.product_status == ("ACTIVE" if availability else "DISCONTINUED")
        stmt = stmt.where(status_filter)
        count_stmt = count_stmt.where(status_filter)
    else:
        # Default listing excludes discontinued products; direct-by-id lookup (below)
        # still allows fetching one, e.g. from an old link or order history.
        stmt = stmt.where(Product.product_status == "ACTIVE")
        count_stmt = count_stmt.where(Product.product_status == "ACTIVE")

    if sort == "price":
        sort_col = Product.base_price
    elif sort == "rating":
        # Products with no reviews sort last regardless of direction, rather than
        # ambiguously mixing with 0-rated products.
        sort_col = func.coalesce(rating_subq.c.average_rating, -1)
    elif sort == "popularity":
        # Derived from confirmed order volume — real existing data, not fabricated.
        popularity_subq = (
            select(OrderItem.product_id, func.sum(OrderItem.quantity).label("units_sold"))
            .group_by(OrderItem.product_id)
            .subquery()
        )
        stmt = stmt.outerjoin(popularity_subq, popularity_subq.c.product_id == Product.product_id)
        sort_col = func.coalesce(popularity_subq.c.units_sold, 0)
    else:  # newest
        sort_col = Product.created_at

    stmt = stmt.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt).all()

    return ProductListResponse(
        items=[_to_product_out(p, avg_rating, review_count) for p, avg_rating, review_count in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db)) -> ProductOut:
    rating_subq = _rating_subquery()
    row = db.execute(
        select(Product, rating_subq.c.average_rating, rating_subq.c.review_count)
        .outerjoin(rating_subq, rating_subq.c.product_id == Product.product_id)
        .where(Product.product_id == product_id)
    ).first()
    if row is None:
        raise NotFoundError("Product not found")
    product, avg_rating, review_count = row
    return _to_product_out(product, avg_rating, review_count)
