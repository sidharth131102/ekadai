import uuid
from decimal import Decimal

from db.models import Category, Product, Review


def _make_product(db_session, category, name, price, status="ACTIVE", brand=None):
    p = Product(
        product_name=name,
        category_id=category.category_id,
        base_price=Decimal(price),
        product_status=status,
        brand=brand,
    )
    db_session.add(p)
    db_session.flush()
    return p


def test_list_categories_only_returns_active(client, db_session):
    active = Category(category_name=f"active-{uuid.uuid4()}", category_status="ACTIVE")
    inactive = Category(category_name=f"inactive-{uuid.uuid4()}", category_status="INACTIVE")
    db_session.add_all([active, inactive])
    db_session.flush()

    resp = client.get("/categories")
    assert resp.status_code == 200
    names = {c["category_name"] for c in resp.json()}
    assert active.category_name in names
    assert inactive.category_name not in names


def test_products_default_listing_excludes_discontinued(client, db_session, category):
    active = _make_product(db_session, category, f"active-{uuid.uuid4()}", "10.00")
    discontinued = _make_product(db_session, category, f"disc-{uuid.uuid4()}", "10.00", status="DISCONTINUED")

    resp = client.get("/products", params={"page_size": 100})
    ids = {p["product_id"] for p in resp.json()["items"]}
    assert str(active.product_id) in ids
    assert str(discontinued.product_id) not in ids


def test_products_search_by_name(client, db_session, category):
    unique = f"Zylophone-{uuid.uuid4()}"
    target = _make_product(db_session, category, unique, "50.00")

    resp = client.get("/products", params={"q": "Zylophone"})
    names = [p["product_name"] for p in resp.json()["items"]]
    assert any(unique == n for n in names)


def test_products_filter_by_price_range(client, db_session, category):
    cheap = _make_product(db_session, category, f"cheap-{uuid.uuid4()}", "5.00")
    pricey = _make_product(db_session, category, f"pricey-{uuid.uuid4()}", "500.00")

    resp = client.get("/products", params={"min_price": "1.00", "max_price": "10.00", "page_size": 100})
    ids = {p["product_id"] for p in resp.json()["items"]}
    assert str(cheap.product_id) in ids
    assert str(pricey.product_id) not in ids


def test_products_sort_by_price_asc(client, db_session, category):
    low = _make_product(db_session, category, f"low-{uuid.uuid4()}", "1.00")
    high = _make_product(db_session, category, f"high-{uuid.uuid4()}", "999.00")

    resp = client.get("/products", params={"sort": "price", "order": "asc", "page_size": 100})
    prices = [Decimal(p["base_price"]) for p in resp.json()["items"]]
    assert prices == sorted(prices)


def test_get_product_not_found(client):
    resp = client.get(f"/products/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_product_allows_discontinued_by_direct_id(client, db_session, category):
    discontinued = _make_product(db_session, category, f"disc-{uuid.uuid4()}", "10.00", status="DISCONTINUED")
    resp = client.get(f"/products/{discontinued.product_id}")
    assert resp.status_code == 200
    assert resp.json()["product_status"] == "DISCONTINUED"


def test_products_blank_query_params_treated_as_unset(client, db_session, category):
    # A frontend <select> for "all categories" / an empty numeric filter naturally
    # submits an empty-string query param, not an absent one — must not 422.
    product = _make_product(db_session, category, f"prod-{uuid.uuid4()}", "10.00")
    resp = client.get(
        "/products",
        params={"category_id": "", "min_price": "", "max_price": "", "brand": ""},
    )
    assert resp.status_code == 200, resp.text
    ids = {p["product_id"] for p in resp.json()["items"]}
    assert str(product.product_id) in ids


def test_products_availability_filter_true_only_active(client, db_session, category):
    active = _make_product(db_session, category, f"active-{uuid.uuid4()}", "10.00")
    discontinued = _make_product(db_session, category, f"disc-{uuid.uuid4()}", "10.00", status="DISCONTINUED")

    resp = client.get("/products", params={"availability": "true", "page_size": 100})
    ids = {p["product_id"] for p in resp.json()["items"]}
    assert str(active.product_id) in ids
    assert str(discontinued.product_id) not in ids


def _add_review(db_session, product, rating, user_id=None, name="Seed Reviewer"):
    db_session.add(Review(product_id=product.product_id, user_id=user_id, reviewer_name=name, rating=rating))
    db_session.flush()


class TestRatingAggregation:
    def test_product_with_no_reviews_has_null_average(self, client, db_session, category):
        product = _make_product(db_session, category, f"unreviewed-{uuid.uuid4()}", "10.00")
        resp = client.get(f"/products/{product.product_id}")
        assert resp.json()["average_rating"] is None
        assert resp.json()["review_count"] == 0

    def test_average_rating_computed_correctly(self, client, db_session, category):
        product = _make_product(db_session, category, f"rated-{uuid.uuid4()}", "10.00")
        _add_review(db_session, product, 5, name="A")
        _add_review(db_session, product, 3, name="B")

        resp = client.get(f"/products/{product.product_id}")
        body = resp.json()
        assert body["average_rating"] == 4.0
        assert body["review_count"] == 2

    def test_sort_by_rating_desc(self, client, db_session, category):
        low = _make_product(db_session, category, f"low-rated-{uuid.uuid4()}", "10.00")
        high = _make_product(db_session, category, f"high-rated-{uuid.uuid4()}", "10.00")
        _add_review(db_session, low, 2, name="A")
        _add_review(db_session, high, 5, name="B")

        resp = client.get("/products", params={"sort": "rating", "order": "desc", "page_size": 100})
        ids_in_order = [p["product_id"] for p in resp.json()["items"]]
        assert ids_in_order.index(str(high.product_id)) < ids_in_order.index(str(low.product_id))

    def test_min_rating_filter_excludes_unreviewed_and_low_rated(self, client, db_session, category):
        unreviewed = _make_product(db_session, category, f"unreviewed-{uuid.uuid4()}", "10.00")
        low = _make_product(db_session, category, f"low-{uuid.uuid4()}", "10.00")
        high = _make_product(db_session, category, f"high-{uuid.uuid4()}", "10.00")
        _add_review(db_session, low, 2, name="A")
        _add_review(db_session, high, 5, name="B")

        resp = client.get("/products", params={"min_rating": "4", "page_size": 100})
        ids = {p["product_id"] for p in resp.json()["items"]}
        assert str(high.product_id) in ids
        assert str(low.product_id) not in ids
        assert str(unreviewed.product_id) not in ids
