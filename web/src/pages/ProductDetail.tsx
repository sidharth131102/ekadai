import { motion } from "framer-motion";
import { ArrowLeft, Heart, ShieldCheck, Truck, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCategories, useProduct } from "../api/hooks/useCatalog";
import { useAddToCart } from "../api/hooks/useCart";
import { useReviews } from "../api/hooks/useReviews";
import { useAddToWishlist, useRemoveFromWishlist, useWishlist } from "../api/hooks/useWishlist";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { StarRating } from "../components/ui/StarRating";
import { ProductVisual } from "../components/product/ProductVisual";
import { QuantityStepper } from "../components/product/QuantityStepper";
import { ReviewForm } from "../components/product/ReviewForm";
import { ReviewList } from "../components/product/ReviewList";
import { Skeleton } from "../components/ui/Skeleton";
import { trackEvent } from "../lib/analytics";
import { fadeIn } from "../lib/motion";
import { formatMoney } from "../lib/format";
import { usePageView } from "../lib/usePageView";
import styles from "./ProductDetail.module.css";

export default function ProductDetail() {
  const { productId } = useParams<{ productId: string }>();
  usePageView("product_detail", productId);
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { showToast } = useToast();
  const { data: product, isLoading } = useProduct(productId);
  const { data: categories } = useCategories();
  const { data: wishlist } = useWishlist();
  const { data: reviews } = useReviews(productId);
  const addToCart = useAddToCart();
  const addToWishlist = useAddToWishlist();
  const removeFromWishlist = useRemoveFromWishlist();
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (product) trackEvent("product_view", { product_id: product.product_id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product?.product_id]);

  if (isLoading || !product) {
    return (
      <div className={["container", styles.page].join(" ")}>
        <div className={styles.layout}>
          <Skeleton height={480} radius="20px" />
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Skeleton height={16} width="30%" />
            <Skeleton height={40} width="80%" />
            <Skeleton height={28} width="20%" />
          </div>
        </div>
      </div>
    );
  }

  const category = categories?.find((c) => c.category_id === product.category_id);
  const wishlistItem = wishlist?.items.find((i) => i.product_id === product.product_id);
  const discontinued = product.product_status === "DISCONTINUED";
  const alreadyReviewed = reviews?.items.some((r) => r.is_own) ?? false;

  function handleAddToCart() {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    addToCart.mutate({ product_id: product!.product_id, quantity });
    showToast(`Added ${quantity} × ${product!.product_name} to your bag`, "success");
  }

  function handleBuyNow() {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    // Client-side correlation id for the click itself — independent of whatever
    // checkout_id the backend mints when /checkout/start is actually called a moment
    // later (§32: this event tracks the click reaching the system, not the outcome).
    trackEvent("buy_now_clicked", {
      product_id: product!.product_id,
      checkout_id: crypto.randomUUID(),
      source: "product_detail",
    });
    navigate("/checkout", { state: { buyNowProduct: product, buyNowQuantity: quantity } });
  }

  function handleToggleWishlist() {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    if (wishlistItem) {
      removeFromWishlist.mutate(wishlistItem.wishlist_item_id);
    } else {
      addToWishlist.mutate(product!.product_id);
      showToast("Saved to wishlist", "success");
    }
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <button className={styles.back} onClick={() => navigate(-1)}>
        <ArrowLeft size={15} /> Back
      </button>

      <div className={styles.layout}>
        <div className={styles.imageWrap}>
          <ProductVisual
            productId={product.product_id}
            imageUrl={product.image_url}
            layoutId={`product-image-${product.product_id}`}
            iconSize={120}
          />
        </div>

        <motion.div variants={fadeIn} initial="hidden" animate="visible">
          {category && <div className={styles.brand}>{category.category_name}</div>}
          {product.brand && <div className={styles.brand}>{product.brand}</div>}
          <h1 className={styles.name}>{product.product_name}</h1>
          <div style={{ marginBottom: "var(--sp-3)" }}>
            <StarRating rating={product.average_rating} count={product.review_count} size={15} />
          </div>

          <div className={styles.priceRow}>
            <span className={styles.price}>{formatMoney(product.base_price)}</span>
            {discontinued ? (
              <Badge tone="neutral">Sold out</Badge>
            ) : (
              <Badge tone="success">In stock</Badge>
            )}
          </div>

          {product.description && <p className={styles.description}>{product.description}</p>}

          <div className={styles.actionsRow}>
            {!discontinued && <QuantityStepper value={quantity} onChange={setQuantity} />}
            <Button size="lg" disabled={discontinued} onClick={handleAddToCart} style={{ flex: 1 }}>
              {discontinued ? "Unavailable" : "Add to bag"}
            </Button>
            <motion.button
              type="button"
              className={styles.wishlistIconButton}
              whileTap={{ scale: 0.85 }}
              onClick={handleToggleWishlist}
              aria-label="Toggle wishlist"
            >
              <Heart
                size={19}
                fill={wishlistItem ? "var(--color-accent)" : "none"}
                color={wishlistItem ? "var(--color-accent)" : "var(--color-ink)"}
              />
            </motion.button>
          </div>

          {!discontinued && (
            <Button variant="secondary" size="lg" fullWidth onClick={handleBuyNow} icon={<Zap size={16} />}>
              Buy now
            </Button>
          )}

          <div className={styles.meta}>
            <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Truck size={16} /> Ships within 2–4 business days
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <ShieldCheck size={16} /> Easy cancellation before an order ships
            </span>
          </div>
        </motion.div>
      </div>

      <div className={styles.reviewsSection}>
        <h2 className={styles.reviewsTitle}>Reviews</h2>
        <div className={styles.reviewsLayout}>
          <ReviewList reviews={reviews?.items ?? []} />
          {isAuthenticated && !alreadyReviewed && <ReviewForm productId={product.product_id} />}
          {isAuthenticated && alreadyReviewed && (
            <p style={{ color: "var(--color-ink-muted)", fontSize: "var(--fs-sm)" }}>
              You've already reviewed this product.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
