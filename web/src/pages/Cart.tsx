import { AnimatePresence, motion } from "framer-motion";
import { ShoppingBag } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCart, useRemoveCartItem, useUpdateCartItem } from "../api/hooks/useCart";
import { Button } from "../components/ui/Button";
import { ProductSwatch } from "../components/product/ProductSwatch";
import { QuantityStepper } from "../components/product/QuantityStepper";
import { formatMoney } from "../lib/format";
import { staggerContainer, staggerItem } from "../lib/motion";
import { usePageView } from "../lib/usePageView";
import styles from "./Cart.module.css";

export default function Cart() {
  usePageView("cart");
  const { data: cart, isLoading } = useCart();
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();
  const navigate = useNavigate();

  const subtotal = (cart?.items ?? []).reduce((sum, item) => sum + Number.parseFloat(item.line_subtotal), 0);

  if (isLoading) return null;

  if (!cart || cart.items.length === 0) {
    return (
      <div className={["container", styles.page].join(" ")}>
        <div className={styles.empty}>
          <ShoppingBag size={40} style={{ opacity: 0.35, marginBottom: 16 }} />
          <h1 className={styles.heading}>Your bag is empty</h1>
          <Button onClick={() => navigate("/products")}>Browse the catalog</Button>
        </div>
      </div>
    );
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <h1 className={styles.heading}>Your bag</h1>
      <div className={styles.layout}>
        <motion.div className={styles.itemsCard} variants={staggerContainer} initial="hidden" animate="visible">
          <AnimatePresence initial={false}>
            {cart.items.map((item) => (
              <motion.div
                key={item.cart_item_id}
                className={styles.row}
                variants={staggerItem}
                layout
                exit={{ opacity: 0, height: 0, marginBottom: 0, paddingBottom: 0 }}
                transition={{ duration: 0.25 }}
              >
                <div className={styles.thumb}>
                  <ProductSwatch seed={item.product_id} iconSize={28} />
                </div>
                <div className={styles.info}>
                  <div className={styles.name}>{item.product_name}</div>
                  <div className={styles.unitPrice}>{formatMoney(item.unit_price)} each</div>
                </div>
                <QuantityStepper
                  value={item.quantity}
                  onChange={(q) => updateItem.mutate({ cartItemId: item.cart_item_id, quantity: q })}
                />
                <div className={styles.rowRight}>
                  <span className={styles.subtotal}>{formatMoney(item.line_subtotal)}</span>
                  <button className={styles.removeButton} onClick={() => removeItem.mutate(item.cart_item_id)}>
                    Remove
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </motion.div>

        <div className={styles.summaryCard}>
          <h2 className={styles.summaryTitle}>Summary</h2>
          <div className={styles.summaryRow}>
            <span>Items</span>
            <span>{cart.total_quantity}</span>
          </div>
          <div className={styles.summaryTotal}>
            <span>Subtotal</span>
            <span>{formatMoney(subtotal)}</span>
          </div>
          <Button fullWidth size="lg" onClick={() => navigate("/checkout")}>
            Proceed to checkout
          </Button>
        </div>
      </div>
    </div>
  );
}
