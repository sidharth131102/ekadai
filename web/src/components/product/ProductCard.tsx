import { motion } from "framer-motion";
import { Heart, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { ProductOut } from "../../api/types";
import { cardHover, staggerItem } from "../../lib/motion";
import { formatMoney } from "../../lib/format";
import { Badge } from "../ui/Badge";
import { StarRating } from "../ui/StarRating";
import { ProductVisual } from "./ProductVisual";
import styles from "./ProductCard.module.css";

interface ProductCardProps {
  product: ProductOut;
  isWishlisted?: boolean;
  onToggleWishlist?: (product: ProductOut) => void;
  onAddToCart?: (product: ProductOut) => void;
}

export function ProductCard({ product, isWishlisted, onToggleWishlist, onAddToCart }: ProductCardProps) {
  const navigate = useNavigate();
  const discontinued = product.product_status === "DISCONTINUED";

  return (
    <motion.article
      variants={staggerItem}
      className={styles.card}
      {...cardHover}
      onClick={() => navigate(`/products/${product.product_id}`)}
    >
      <div className={styles.imageWrap}>
        {discontinued && (
          <div className={styles.discontinued}>
            <Badge tone="neutral">Sold out</Badge>
          </div>
        )}
        {onToggleWishlist && (
          <motion.button
            type="button"
            className={styles.wishlistButton}
            whileTap={{ scale: 0.8 }}
            onClick={(e) => {
              e.stopPropagation();
              onToggleWishlist(product);
            }}
            aria-label={isWishlisted ? "Remove from wishlist" : "Add to wishlist"}
          >
            <motion.span
              animate={isWishlisted ? { scale: [1, 1.3, 1] } : { scale: 1 }}
              transition={{ duration: 0.3 }}
              style={{ display: "flex" }}
            >
              <Heart
                size={16}
                fill={isWishlisted ? "var(--color-accent)" : "none"}
                color={isWishlisted ? "var(--color-accent)" : "var(--color-ink)"}
              />
            </motion.span>
          </motion.button>
        )}
        <ProductVisual
          productId={product.product_id}
          imageUrl={product.image_url}
          layoutId={`product-image-${product.product_id}`}
        />
      </div>
      <div className={styles.body}>
        {product.brand && <span className={styles.brand}>{product.brand}</span>}
        <h3 className={styles.name}>{product.product_name}</h3>
        <StarRating rating={product.average_rating} count={product.review_count} size={12} />
        <div className={styles.footer}>
          <span className={styles.price}>{formatMoney(product.base_price)}</span>
          {onAddToCart && !discontinued && (
            <motion.button
              type="button"
              className={styles.addButton}
              whileTap={{ scale: 0.85 }}
              whileHover={{ scale: 1.08 }}
              onClick={(e) => {
                e.stopPropagation();
                onAddToCart(product);
              }}
              aria-label="Add to cart"
            >
              <Plus size={16} />
            </motion.button>
          )}
        </div>
      </div>
    </motion.article>
  );
}
