import { motion } from "framer-motion";
import { PackageSearch } from "lucide-react";
import type { ProductOut } from "../../api/types";
import { staggerContainer } from "../../lib/motion";
import { Skeleton } from "../ui/Skeleton";
import { ProductCard } from "./ProductCard";
import styles from "./ProductGrid.module.css";

interface ProductGridProps {
  products: ProductOut[] | undefined;
  isLoading: boolean;
  wishlistedIds?: Set<string>;
  onToggleWishlist?: (product: ProductOut) => void;
  onAddToCart?: (product: ProductOut) => void;
  emptyMessage?: string;
}

export function ProductGrid({
  products,
  isLoading,
  wishlistedIds,
  onToggleWishlist,
  onAddToCart,
  emptyMessage = "Nothing here yet.",
}: ProductGridProps) {
  if (isLoading) {
    return (
      <div className={styles.grid}>
        {Array.from({ length: 8 }).map((_, i) => (
          <div className={styles.skeletonCard} key={i}>
            <Skeleton height={260} width="100%" radius="12px" />
            <Skeleton height={14} width="60%" />
            <Skeleton height={18} width="85%" />
            <Skeleton height={16} width="40%" />
          </div>
        ))}
      </div>
    );
  }

  if (!products || products.length === 0) {
    return (
      <div className={styles.grid}>
        <div className={styles.empty}>
          <PackageSearch size={36} style={{ margin: "0 auto var(--sp-3)", opacity: 0.5 }} />
          <p className={styles.emptyTitle}>No products found</p>
          <p>{emptyMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div className={styles.grid} variants={staggerContainer} initial="hidden" animate="visible">
      {products.map((product) => (
        <ProductCard
          key={product.product_id}
          product={product}
          isWishlisted={wishlistedIds?.has(product.product_id)}
          onToggleWishlist={onToggleWishlist}
          onAddToCart={onAddToCart}
        />
      ))}
    </motion.div>
  );
}
