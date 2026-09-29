"""Import every model module so `Base.metadata` is fully populated for Alembic
autogenerate and `Base.metadata.create_all()`."""

from db.models.base import Base
from db.models.cart_wishlist import Cart, CartItem, Wishlist, WishlistItem
from db.models.catalog import Category, Product
from db.models.orders import Order, OrderItem
from db.models.promotions import Promotion, PromotionTarget
from db.models.reviews import Review
from db.models.users import Address, User

__all__ = [
    "Base",
    "User",
    "Address",
    "Category",
    "Product",
    "Promotion",
    "PromotionTarget",
    "Cart",
    "CartItem",
    "Wishlist",
    "WishlistItem",
    "Order",
    "OrderItem",
    "Review",
]
