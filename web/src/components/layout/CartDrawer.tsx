import { AnimatePresence, motion } from "framer-motion";
import { ShoppingBag, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useCart, useRemoveCartItem, useUpdateCartItem } from "../../api/hooks/useCart";
import { useCartDrawer } from "../../context/CartDrawerContext";
import { backdropVariants, drawerVariants } from "../../lib/motion";
import { formatMoney } from "../../lib/format";
import { Button } from "../ui/Button";
import { ProductSwatch } from "../product/ProductSwatch";
import { QuantityStepper } from "../product/QuantityStepper";
import styles from "./CartDrawer.module.css";

export function CartDrawer() {
  const { isOpen, close } = useCartDrawer();
  const { data: cart } = useCart();
  const updateItem = useUpdateCartItem();
  const removeItem = useRemoveCartItem();
  const navigate = useNavigate();

  const subtotal = (cart?.items ?? []).reduce((sum, item) => sum + Number.parseFloat(item.line_subtotal), 0);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            style={{ position: "fixed", inset: 0, background: "rgba(36,28,21,0.4)", zIndex: 200 }}
            onClick={close}
          />
          <motion.aside
            className={styles.drawer}
            variants={drawerVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            <div className={styles.header}>
              <h2 className={styles.title}>Your bag</h2>
              <button className={styles.closeButton} onClick={close} aria-label="Close cart">
                <X size={20} />
              </button>
            </div>

            {!cart || cart.items.length === 0 ? (
              <div className={styles.empty}>
                <ShoppingBag size={36} style={{ opacity: 0.4 }} />
                <p>Your bag is empty.</p>
                <Button
                  variant="secondary"
                  onClick={() => {
                    close();
                    navigate("/products");
                  }}
                >
                  Browse products
                </Button>
              </div>
            ) : (
              <div className={styles.items}>
                <AnimatePresence initial={false}>
                  {cart.items.map((item) => (
                    <motion.div
                      key={item.cart_item_id}
                      className={styles.item}
                      layout
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                      transition={{ duration: 0.25 }}
                    >
                      <div className={styles.itemImage}>
                        <ProductSwatch seed={item.product_id} iconSize={20} />
                      </div>
                      <div className={styles.itemInfo}>
                        <div className={styles.itemName}>{item.product_name}</div>
                        <div className={styles.itemPrice}>{formatMoney(item.unit_price)} each</div>
                        <button
                          className={styles.removeButton}
                          onClick={() => removeItem.mutate(item.cart_item_id)}
                        >
                          Remove
                        </button>
                      </div>
                      <div className={styles.itemActions}>
                        <span style={{ fontWeight: 700, fontSize: "var(--fs-sm)" }}>
                          {formatMoney(item.line_subtotal)}
                        </span>
                        <QuantityStepper
                          value={item.quantity}
                          onChange={(q) => updateItem.mutate({ cartItemId: item.cart_item_id, quantity: q })}
                        />
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            )}

            {cart && cart.items.length > 0 && (
              <div className={styles.footer}>
                <div className={styles.subtotalRow}>
                  <span>Subtotal</span>
                  <span>{formatMoney(subtotal)}</span>
                </div>
                <Button
                  fullWidth
                  size="lg"
                  onClick={() => {
                    close();
                    navigate("/checkout");
                  }}
                >
                  Checkout
                </Button>
              </div>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
