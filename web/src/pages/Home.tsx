import { motion } from "framer-motion";
import { ArrowRight, Sparkle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCategories, useProducts } from "../api/hooks/useCatalog";
import { useAddToCart } from "../api/hooks/useCart";
import { useAddToWishlist, useRemoveFromWishlist, useWishlist } from "../api/hooks/useWishlist";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { ProductGrid } from "../components/product/ProductGrid";
import { ProductSwatch } from "../components/product/ProductSwatch";
import { fadeIn, staggerContainer, staggerItem } from "../lib/motion";
import { usePageView } from "../lib/usePageView";
import type { ProductOut } from "../api/types";
import styles from "./Home.module.css";

export default function Home() {
  usePageView("home");
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const { showToast } = useToast();
  const { data: categories } = useCategories();
  const { data: featured, isLoading } = useProducts({ sort: "newest", order: "desc", page_size: 8 });
  const { data: wishlist } = useWishlist();
  const addToCart = useAddToCart();
  const addToWishlist = useAddToWishlist();
  const removeFromWishlist = useRemoveFromWishlist();

  const wishlistedIds = new Set((wishlist?.items ?? []).map((i) => i.product_id));
  const collageProducts = featured?.items.slice(0, 3) ?? [];

  function handleAddToCart(product: ProductOut) {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    addToCart.mutate({ product_id: product.product_id, quantity: 1 });
    showToast(`Added ${product.product_name} to your bag`, "success");
  }

  function handleToggleWishlist(product: ProductOut) {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    const existing = wishlist?.items.find((i) => i.product_id === product.product_id);
    if (existing) {
      removeFromWishlist.mutate(existing.wishlist_item_id);
    } else {
      addToWishlist.mutate(product.product_id);
      showToast(`Saved ${product.product_name} to your wishlist`, "success");
    }
  }

  return (
    <div>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
            <motion.div variants={staggerItem} className={styles.eyebrow}>
              <Sparkle size={14} /> Seven categories, considered carefully
            </motion.div>
            <motion.h1 variants={staggerItem} className={styles.headline}>
              Everything you need, <em>nothing</em> you don't.
            </motion.h1>
            <motion.p variants={staggerItem} className={styles.heroCopy}>
              A small, deliberately-curated catalog — electronics to beauty — with the fuss
              of ordinary online shopping removed.
            </motion.p>
            <motion.div variants={staggerItem} className={styles.heroActions}>
              <motion.button
                className={styles.categoryChip}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.96 }}
                onClick={() => navigate("/products")}
                style={{ background: "var(--color-accent)", color: "var(--color-accent-ink)", border: "none" }}
              >
                Shop the catalog <ArrowRight size={15} />
              </motion.button>
            </motion.div>
          </motion.div>

          <motion.div
            className={styles.collage}
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.15 }}
          >
            {collageProducts[0] && (
              <div className={[styles.collageTile, styles.tile1].join(" ")}>
                <ProductSwatch seed={collageProducts[0].product_id} iconSize={64} />
              </div>
            )}
            {collageProducts[1] && (
              <div className={[styles.collageTile, styles.tile2].join(" ")}>
                <ProductSwatch seed={collageProducts[1].product_id} iconSize={44} />
              </div>
            )}
            {collageProducts[2] && (
              <div className={[styles.collageTile, styles.tile3].join(" ")}>
                <ProductSwatch seed={collageProducts[2].product_id} iconSize={36} />
              </div>
            )}
          </motion.div>
        </div>
      </section>

      {categories && categories.length > 0 && (
        <motion.div
          className={styles.chipsRow}
          initial="hidden"
          animate="visible"
          variants={staggerContainer}
        >
          {categories.map((category) => (
            <motion.button
              key={category.category_id}
              variants={staggerItem}
              className={styles.categoryChip}
              whileHover={{ y: -3, borderColor: "var(--color-accent)" }}
              whileTap={{ scale: 0.96 }}
              onClick={() => navigate(`/products?category_id=${category.category_id}`)}
            >
              {category.category_name}
            </motion.button>
          ))}
        </motion.div>
      )}

      <motion.section
        className={styles.section}
        variants={fadeIn}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
      >
        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>Newly added</h2>
          <button className={styles.sectionLink} onClick={() => navigate("/products")}>
            View all →
          </button>
        </div>
        <ProductGrid
          products={featured?.items}
          isLoading={isLoading}
          wishlistedIds={wishlistedIds}
          onToggleWishlist={handleToggleWishlist}
          onAddToCart={handleAddToCart}
        />
      </motion.section>
    </div>
  );
}
