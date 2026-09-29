"""Generates sample review content for seeding (Phase 2c — user explicitly chose seeded
sample reviews over an empty or skipped reviews feature). Deterministic (seeded RNG keyed by
product name) so re-running the seed script produces identical output — required for
`run_seed.py`'s idempotency guarantee.

This is clearly-labeled demo content: reviewer_name here never corresponds to a real
registered user (reviews.user_id is NULL for every row this produces), which is the
truthful way to represent "sample reviews" rather than inventing fake user accounts to
back them.
"""

from __future__ import annotations

import random

REVIEWER_NAMES = [
    "Aditi Rao", "Rahul Mehta", "Sneha Kapoor", "Vikram Nair", "Priya Sharma",
    "Arjun Iyer", "Neha Gupta", "Karan Singh", "Ananya Reddy", "Rohan Verma",
    "Ishita Joshi", "Aman Malhotra", "Divya Menon", "Siddharth Rao", "Pooja Desai",
    "Kabir Kapoor", "Meera Pillai", "Nikhil Chatterjee", "Tanya Bhatt", "Yash Agarwal",
]

# (rating, templates) — weighted so the distribution reads like a real store, not a
# five-star wall (45% 5-star / 35% 4-star / 15% 3-star / 5% 2-star).
TEMPLATES: list[tuple[int, list[str]]] = [
    (
        5,
        [
            "Exactly what I needed — it's been solid every day since it arrived.",
            "Genuinely impressed, the quality feels well above the price point.",
            "Works exactly as described, no surprises at all. Would buy again.",
            "Best purchase I've made in this category in a while.",
            "Arrived quickly and exceeded what I expected for the price.",
            "Couldn't be happier — this is exactly what the listing promised.",
        ],
    ),
    (
        4,
        [
            "Really happy with this, though the packaging could've been sturdier.",
            "Does what it promises. Only docking a star because delivery took a bit longer than expected.",
            "Solid quality for the price. Minor wear after a few weeks but nothing concerning.",
            "Good value overall — a couple of small things keep it from being perfect.",
            "Happy with the purchase, would recommend to a friend with minor reservations.",
        ],
    ),
    (
        3,
        [
            "It's fine, does the job, but I expected a bit more given the price.",
            "Average. Not bad, but nothing about it really stood out either.",
            "Works as intended, though customer support was slow when I had a question.",
        ],
    ),
    (
        2,
        [
            "Didn't quite meet my expectations, wouldn't rush to reorder.",
            "It's okay, but I've had better from other brands at this price.",
        ],
    ),
]

_WEIGHTS = [45, 35, 15, 5]  # aligned to TEMPLATES order


def generate_reviews_for_product(product_name: str, review_count: int = 3) -> list[dict]:
    rng = random.Random(product_name)  # deterministic per product, stable across re-runs
    reviewers = rng.sample(REVIEWER_NAMES, k=min(review_count, len(REVIEWER_NAMES)))

    reviews = []
    for reviewer_name in reviewers:
        rating, templates = rng.choices(TEMPLATES, weights=_WEIGHTS, k=1)[0]
        review_text = rng.choice(templates)
        reviews.append({"reviewer_name": reviewer_name, "rating": rating, "review_text": review_text})
    return reviews
