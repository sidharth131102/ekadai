"""Simulated shopper traffic through the REAL application API.

Not fabricated warehouse data (§106): every action goes through the running FastAPI app exactly
like the React frontend — real registrations, carts, checkouts and orders land in Postgres
(→ Debezium CDC), and every behavioral event goes through the real producer (→ Kafka → Bronze →
Silver → Gold). The only simulated part is the person clicking. Everything it creates is
labelled: emails `sim-…@example.com`, session ids `sim-…`, so simulated traffic is always
distinguishable from real users.

Usage (app running with EVENT_TRANSPORT=kafka):
    python scripts/simulate_traffic.py --sessions 40 --api http://localhost:8000
"""

from __future__ import annotations

import argparse
import random
import time
import uuid

import httpx

CITIES = [("Kochi", "KL"), ("Bengaluru", "KA"), ("Chennai", "TN"), ("Mumbai", "MH"), ("Pune", "MH"),
          ("Hyderabad", "TG"), ("Delhi", "DL"), ("Kolkata", "WB")]
QUERIES = ["earbuds", "lamp", "pillow", "charger", "bottle", "kettle", "shoes", "backpack", "watch", "mug"]
PASSWORD = "sim-traffic-pass"


def now_ms() -> int:
    return int(time.time() * 1000)


class Shopper:
    def __init__(self, api: str, rng: random.Random, products: list[dict], categories: list[dict]):
        self.api, self.rng, self.products, self.categories = api, rng, products, categories
        self.email = f"sim-{uuid.uuid4().hex[:10]}@example.com"
        self.city, self.state = rng.choice(CITIES)
        self.token: str | None = None
        self.address_id: str | None = None

    def client(self, session_id: str) -> httpx.Client:
        headers = {"X-Session-Id": session_id, "User-Agent": self.rng.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile Safari/604.1",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/128.0 Mobile Safari/537.36",
        ])}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.Client(base_url=self.api, headers=headers, timeout=30)

    def event(self, c: httpx.Client, event_type: str, payload: dict) -> None:
        c.post("/events", json={"event_type": event_type, "event_timestamp": now_ms(), "payload": payload})

    def pause(self, lo=0.3, hi=1.5) -> None:
        time.sleep(self.rng.uniform(lo, hi))

    def session(self) -> str:
        """One browsing session. Returns the furthest funnel stage reached."""
        rng = self.rng
        sid = f"sim-{uuid.uuid4()}"
        c = self.client(sid)
        stage = "browse"
        self.event(c, "page_view", {"page_type": "home", "product_id": None, "category_id": None})

        if self.token is None and rng.random() < 0.6:
            r = c.post("/auth/register", json={"email": self.email, "password": PASSWORD, "city": self.city, "state": self.state})
            r.raise_for_status()
            self.token = r.json()["access_token"]
            c = self.client(sid)  # same session continues authenticated (§83)
        elif self.token is not None and rng.random() < 0.3:
            r = c.post("/auth/login", json={"email": self.email, "password": PASSWORD})
            r.raise_for_status()
            self.token = r.json()["access_token"]
            c = self.client(sid)

        if rng.random() < 0.6:
            q = rng.choice(QUERIES)
            hits = c.get("/products", params={"q": q}).json()
            self.event(c, "search", {"search_query": q, "search_result_count": hits.get("total", 0)})
            self.pause()
        if rng.random() < 0.4:
            cat = rng.choice(self.categories)
            self.event(c, "filter_applied", {"filters": [
                {"filter_type": "category", "filter_value_string": None, "filter_value_min": None,
                 "filter_value_max": None, "filter_value_boolean": None, "category_id": cat["category_id"]},
                {"filter_type": "price", "filter_value_string": None, "filter_value_min": 0.0,
                 "filter_value_max": float(rng.choice([1000, 2500, 5000, 10000])), "filter_value_boolean": None,
                 "category_id": None},
            ]})
        if rng.random() < 0.3:
            self.event(c, "sort_applied", {"sort_field": rng.choice(["price", "rating"]), "sort_direction": rng.choice(["asc", "desc"])})

        viewed = rng.sample(self.products, k=rng.randint(1, 4))
        for p in viewed:
            self.event(c, "page_view", {"page_type": "product_detail", "product_id": p["product_id"], "category_id": p["category_id"]})
            self.event(c, "product_view", {"product_id": p["product_id"]})
            self.pause()
        stage = "view"

        if self.token is None:
            return stage  # anonymous visitors only browse
        if rng.random() < 0.25:
            c.post("/wishlist/items", json={"product_id": viewed[0]["product_id"]})

        if rng.random() < 0.55:
            for p in rng.sample(viewed, k=rng.randint(1, len(viewed))):
                c.post("/cart/items", json={"product_id": p["product_id"], "quantity": rng.randint(1, 3)}).raise_for_status()
                self.pause(0.2, 0.8)
            stage = "cart"
            cart = c.get("/cart").json()
            if len(cart["items"]) > 1 and rng.random() < 0.3:
                c.delete(f"/cart/items/{cart['items'][0]['cart_item_id']}")

            if rng.random() < 0.6 and c.get("/cart").json()["items"]:
                chk = c.post("/checkout/start", json={})
                chk.raise_for_status()
                stage = "checkout"
                self.pause()
                if rng.random() < 0.7:  # the rest abandon the checkout
                    if self.address_id is None:
                        a = c.post("/users/me/addresses", json={
                            "address_line1": f"{rng.randint(1, 200)} Sim Street", "city": self.city, "state": self.state,
                            "postal_code": f"{rng.randint(100000, 999999)}", "country": "IN", "is_default": True})
                        a.raise_for_status()
                        self.address_id = a.json()["address_id"]
                    o = c.post("/orders", json={"checkout_id": chk.json()["checkout_id"], "address_id": self.address_id})
                    o.raise_for_status()
                    stage = "order"
                    order_id = o.json()["order_id"]
                    self.event(c, "order_viewed", {"order_id": order_id, "page_context": "order_detail"})
                    if rng.random() < 0.15:
                        self.pause()
                        c.post(f"/orders/{order_id}/cancel").raise_for_status()
                        stage = "cancelled"
        return stage


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--sessions", type=int, default=40)
    ap.add_argument("--shoppers", type=int, default=15)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    with httpx.Client(base_url=args.api, timeout=30) as c:
        products = c.get("/products", params={"page_size": 100}).json()["items"]
        categories = c.get("/categories").json()
    shoppers = [Shopper(args.api, rng, products, categories) for _ in range(args.shoppers)]
    tally: dict[str, int] = {}
    for i in range(args.sessions):
        shopper = rng.choice(shoppers)
        try:
            stage = shopper.session()
        except httpx.HTTPError as exc:
            stage = f"error:{type(exc).__name__}"
        tally[stage] = tally.get(stage, 0) + 1
        print(f"session {i + 1}/{args.sessions}: {stage}")
    print("summary:", tally)


if __name__ == "__main__":
    main()
