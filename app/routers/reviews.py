from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, get_optional_current_user
from app.errors import ConflictError, NotFoundError
from app.schemas.reviews import ReviewCreateRequest, ReviewListResponse, ReviewOut
from db.models import Product, Review, User

router = APIRouter(prefix="/products", tags=["reviews"])


@router.get("/{product_id}/reviews", response_model=ReviewListResponse)
def list_reviews(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
) -> ReviewListResponse:
    if db.get(Product, product_id) is None:
        raise NotFoundError("Product not found")

    reviews = db.execute(
        select(Review).where(Review.product_id == product_id).order_by(Review.created_at.desc())
    ).scalars().all()
    average_rating = db.execute(
        select(func.avg(Review.rating)).where(Review.product_id == product_id)
    ).scalar_one()

    items = [
        ReviewOut(
            review_id=r.review_id,
            reviewer_name=r.reviewer_name,
            rating=r.rating,
            review_text=r.review_text,
            created_at=r.created_at,
            is_own=bool(current_user and r.user_id == current_user.user_id),
        )
        for r in reviews
    ]
    return ReviewListResponse(
        items=items,
        total=len(items),
        average_rating=round(average_rating, 1) if average_rating is not None else None,
    )


@router.post("/{product_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    product_id: uuid.UUID,
    payload: ReviewCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewOut:
    if db.get(Product, product_id) is None:
        raise NotFoundError("Product not found")

    review = Review(
        product_id=product_id,
        user_id=current_user.user_id,
        reviewer_name=payload.reviewer_name,
        rating=payload.rating,
        review_text=payload.review_text,
    )
    db.add(review)
    try:
        # flush (not commit) so a constraint failure doesn't end the transaction the way
        # a failed commit would — same pattern as app/services/orders.py's checkout_id
        # collision handling.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("You've already reviewed this product") from exc
    db.commit()
    db.refresh(review)

    return ReviewOut(
        review_id=review.review_id,
        reviewer_name=review.reviewer_name,
        rating=review.rating,
        review_text=review.review_text,
        created_at=review.created_at,
        is_own=True,
    )
