import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAddToCart } from "../api/hooks/useCart";
import { useRemoveFromWishlist, useWishlist } from "../api/hooks/useWishlist";
import { useToast } from "../context/ToastContext";
import { Button } from "../components/ui/Button";
import { ProductGrid } from "../components/product/ProductGrid";
import { trackEvent } from "../lib/analytics";
import { usePageView } from "../lib/usePageView";
import type { ProductOut } from "../api/types";
import styles from "./ProductListing.module.css";

export default function Wishlist() {
  usePageView("wishlist");
  const { data: wishlist, isLoading } = useWishlist();
  const removeFromWishlist = useRemoveFromWishlist();
  const addToCart = useAddToCart();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const wishlistId = wishlist?.wishlist_id;
  useEffect(() => {
    if (wishlistId) trackEvent("wishlist_view", { wishlist_id: wishlistId });
  }, [wishlistId]);

  // WishlistItemOut doesn't carry category_id/brand — adapt to ProductOut's shape for the
  // shared card (category_id is never rendered there; brand becomes null → hidden).
  const products: ProductOut[] =
    wishlist?.items.map((item) => ({
      product_id: item.product_id,
      product_name: item.product_name,
      category_id: "",
      brand: null,
      base_price: item.base_price,
      product_status: item.product_status,
      description: null,
      image_url: null,
      average_rating: null,
      review_count: 0,
    })) ?? [];

  const wishlistedIds = new Set(products.map((p) => p.product_id));

  function handleToggleWishlist(product: ProductOut) {
    const item = wishlist?.items.find((i) => i.product_id === product.product_id);
    if (item) removeFromWishlist.mutate(item.wishlist_item_id);
  }

  function handleAddToCart(product: ProductOut) {
    addToCart.mutate({ product_id: product.product_id, quantity: 1 });
    showToast(`Added ${product.product_name} to your bag`, "success");
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <h1 className={styles.heading}>Your wishlist</h1>
      <p className={styles.resultCount}>{products.length} saved items</p>
      <ProductGrid
        products={products}
        isLoading={isLoading}
        wishlistedIds={wishlistedIds}
        onToggleWishlist={handleToggleWishlist}
        onAddToCart={handleAddToCart}
        emptyMessage="Tap the heart on any product to save it here."
      />
      {products.length === 0 && !isLoading && (
        <div style={{ textAlign: "center", marginTop: 24 }}>
          <Button variant="secondary" onClick={() => navigate("/products")}>
            Browse the catalog →
          </Button>
        </div>
      )}
    </div>
  );
}
