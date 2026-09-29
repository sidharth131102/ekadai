"""Promotion resolution engine — one batched query per checkout/order-creation call,
independent of cart size. Design per the Phase 2a plan's "Checkout / order-creation
transaction" section (§17-§18 business rules: highest-priority eligible promotion wins,
promotions do not stack).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from db.models.promotions import Promotion, PromotionTarget

# Convention: higher integer = higher priority. Not specified by the schema/spec —
# documented here since it's the one place the direction matters.
PROMOTION_STATUS_ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class PromotionCandidate:
    promotion_id: uuid.UUID
    target_type: str
    product_id: uuid.UUID | None
    category_id: uuid.UUID | None
    discount_type: str
    discount_value: Decimal
    priority: int
    created_at: datetime


def find_eligible_candidates(
    session: Session,
    product_ids: list[uuid.UUID],
    category_ids: list[uuid.UUID],
    now: datetime,
) -> list[PromotionCandidate]:
    stmt = (
        select(
            PromotionTarget.target_type,
            PromotionTarget.product_id,
            PromotionTarget.category_id,
            Promotion.promotion_id,
            Promotion.discount_type,
            Promotion.discount_value,
            Promotion.priority,
            Promotion.created_at,
        )
        .join(Promotion, Promotion.promotion_id == PromotionTarget.promotion_id)
        .where(
            Promotion.promotion_status == PROMOTION_STATUS_ACTIVE,
            Promotion.start_at <= now,
            or_(Promotion.end_at.is_(None), Promotion.end_at > now),
            or_(
                and_(
                    PromotionTarget.target_type == "PRODUCT",
                    PromotionTarget.product_id.in_(product_ids),
                ),
                and_(
                    PromotionTarget.target_type == "CATEGORY",
                    PromotionTarget.category_id.in_(category_ids),
                ),
                PromotionTarget.target_type == "SITEWIDE",
            ),
        )
    )
    rows = session.execute(stmt).all()
    return [
        PromotionCandidate(
            promotion_id=row.promotion_id,
            target_type=row.target_type,
            product_id=row.product_id,
            category_id=row.category_id,
            discount_type=row.discount_type,
            discount_value=row.discount_value,
            priority=row.priority,
            created_at=row.created_at,
        )
        for row in rows
    ]


def resolve_best_promotion(
    candidates: list[PromotionCandidate],
    product_id: uuid.UUID,
    category_id: uuid.UUID,
) -> PromotionCandidate | None:
    matches = [
        c
        for c in candidates
        if (c.target_type == "PRODUCT" and c.product_id == product_id)
        or (c.target_type == "CATEGORY" and c.category_id == category_id)
        or c.target_type == "SITEWIDE"
    ]
    if not matches:
        return None
    # Highest priority wins; ties broken by earlier created_at, then promotion_id as a
    # final deterministic tiebreak.
    return min(matches, key=lambda c: (-c.priority, c.created_at, str(c.promotion_id)))


def compute_discount(
    unit_price: Decimal, quantity: int, promotion: PromotionCandidate | None
) -> tuple[Decimal, Decimal]:
    """Returns (discount_amount, line_revenue). Never floats; rounds once, then clamps
    into the DB's `discount_amount <= quantity * unit_price` bound."""
    gross = unit_price * quantity
    if promotion is None:
        return Decimal("0.00"), gross

    if promotion.discount_type == "PERCENTAGE":
        raw_discount = gross * promotion.discount_value / Decimal(100)
    else:  # FIXED_AMOUNT — a flat amount per unit, scaled by quantity (see plan rationale)
        raw_discount = promotion.discount_value * quantity

    discount = raw_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    discount = min(max(discount, Decimal("0.00")), gross)
    line_revenue = gross - discount
    return discount, line_revenue
