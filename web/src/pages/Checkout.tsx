import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAddresses, useCreateAddress } from "../api/hooks/useAddresses";
import { useCart } from "../api/hooks/useCart";
import { useStartCheckout } from "../api/hooks/useCheckout";
import { useCreateOrder } from "../api/hooks/useOrders";
import type { AddressCreateRequest, ProductOut } from "../api/types";
import { ApiError } from "../api/client";
import { AnimatedCheckmark } from "../components/ui/AnimatedCheckmark";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { formatMoney } from "../lib/format";
import { fadeIn, scaleIn } from "../lib/motion";
import { useCountUp } from "../lib/useCountUp";
import { usePageView } from "../lib/usePageView";
import styles from "./Checkout.module.css";

type Step = "address" | "review" | "success";

const EMPTY_ADDRESS: AddressCreateRequest = {
  address_line1: "",
  city: "",
  state: "",
  postal_code: "",
  country: "US",
  is_default: false,
};

interface BuyNowLocationState {
  buyNowProduct?: ProductOut;
  buyNowQuantity?: number;
}

export default function Checkout() {
  usePageView("checkout");
  const navigate = useNavigate();
  const location = useLocation();
  const { buyNowProduct, buyNowQuantity } = (location.state as BuyNowLocationState | null) ?? {};
  const buyNow = buyNowProduct && buyNowQuantity ? { product_id: buyNowProduct.product_id, quantity: buyNowQuantity } : undefined;

  const { data: cart } = useCart();
  const { data: addresses, isLoading: addressesLoading } = useAddresses();
  const createAddress = useCreateAddress();
  const startCheckout = useStartCheckout();
  const createOrder = useCreateOrder();

  const [step, setStep] = useState<Step>("address");
  const [selectedAddressId, setSelectedAddressId] = useState<string | null>(null);
  const [showNewAddressForm, setShowNewAddressForm] = useState(false);
  const [newAddress, setNewAddress] = useState<AddressCreateRequest>(EMPTY_ADDRESS);
  const [error, setError] = useState<string | null>(null);
  const [placedOrder, setPlacedOrder] = useState<Awaited<ReturnType<typeof createOrder.mutateAsync>> | null>(
    null,
  );

  useEffect(() => {
    if (!addresses || addresses.length === 0) {
      setShowNewAddressForm(true);
      return;
    }
    if (!selectedAddressId) {
      const preferred = addresses.find((a) => a.is_default) ?? addresses[0];
      setSelectedAddressId(preferred.address_id);
    }
  }, [addresses, selectedAddressId]);

  async function handleAddAddress(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await createAddress.mutateAsync(newAddress);
      setSelectedAddressId(created.address_id);
      setShowNewAddressForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that address.");
    }
  }

  async function handleProceedToReview() {
    if (!selectedAddressId) return;
    setError(null);
    try {
      await startCheckout.mutateAsync(buyNow);
      setStep("review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start checkout.");
    }
  }

  async function handleConfirmOrder() {
    if (!selectedAddressId || !startCheckout.data) return;
    setError(null);
    try {
      const order = await createOrder.mutateAsync({
        checkout_id: startCheckout.data.checkout_id,
        address_id: selectedAddressId,
        buy_now: buyNow,
      });
      setPlacedOrder(order);
      setStep("success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not place your order.");
    }
  }

  const snapshot = startCheckout.data;
  // Hooks must run unconditionally on every render — these stay above the early return
  // below, even though their result is only used once `step === "review"`.
  const gmv = useCountUp(snapshot ? Number.parseFloat(snapshot.gross_merchandise_value) : 0);
  const discount = useCountUp(snapshot ? Number.parseFloat(snapshot.discount_amount) : 0);
  const net = useCountUp(snapshot ? Number.parseFloat(snapshot.cart_net_value) : 0);

  if (!buyNow && !addressesLoading && (!cart || cart.items.length === 0) && step !== "success") {
    return (
      <div className={["container", styles.page].join(" ")}>
        <div className={styles.card} style={{ textAlign: "center" }}>
          <p style={{ marginBottom: 16 }}>Your bag is empty — add something before checking out.</p>
          <Button onClick={() => navigate("/products")}>Browse the catalog</Button>
        </div>
      </div>
    );
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <div className={styles.stepper}>
        <StepDot label="Address" active={step === "address"} done={step !== "address"} />
        <div className={styles.stepLine} />
        <StepDot label="Review" active={step === "review"} done={step === "success"} />
        <div className={styles.stepLine} />
        <StepDot label="Confirmed" active={step === "success"} done={false} />
      </div>

      {error && (
        <div style={{ marginBottom: 16, color: "var(--color-danger)", fontSize: "var(--fs-sm)" }}>{error}</div>
      )}

      <AnimatePresence mode="wait">
        {step === "address" && (
          <motion.div key="address" variants={fadeIn} initial="hidden" animate="visible" exit="hidden" className={styles.card}>
            <h2 className={styles.sectionTitle}>Where should we ship this?</h2>

            {addresses && addresses.length > 0 && (
              <div className={styles.addressList}>
                {addresses.map((address) => (
                  <button
                    key={address.address_id}
                    type="button"
                    className={[
                      styles.addressCard,
                      selectedAddressId === address.address_id ? styles.addressCardSelected : "",
                    ].join(" ")}
                    onClick={() => setSelectedAddressId(address.address_id)}
                  >
                    <span className={styles.addressRadio}>
                      {selectedAddressId === address.address_id && <Check size={12} />}
                    </span>
                    <span className={styles.addressLines}>
                      {address.address_line1}
                      {address.address_line2 ? `, ${address.address_line2}` : ""}
                      <br />
                      {address.city}, {address.state} {address.postal_code}
                      <br />
                      {address.country} {address.is_default && "· Default"}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {!showNewAddressForm && (
              <Button variant="secondary" size="sm" onClick={() => setShowNewAddressForm(true)}>
                + Add a new address
              </Button>
            )}

            {showNewAddressForm && (
              <motion.form
                variants={scaleIn}
                initial="hidden"
                animate="visible"
                onSubmit={handleAddAddress}
                className={styles.newAddressForm}
                style={{ marginTop: 16 }}
              >
                <Input
                  label="Address line 1"
                  required
                  value={newAddress.address_line1}
                  onChange={(e) => setNewAddress({ ...newAddress, address_line1: e.target.value })}
                />
                <Input
                  label="City"
                  required
                  value={newAddress.city}
                  onChange={(e) => setNewAddress({ ...newAddress, city: e.target.value })}
                />
                <Input
                  label="State"
                  required
                  value={newAddress.state}
                  onChange={(e) => setNewAddress({ ...newAddress, state: e.target.value })}
                />
                <Input
                  label="Postal code"
                  required
                  value={newAddress.postal_code}
                  onChange={(e) => setNewAddress({ ...newAddress, postal_code: e.target.value })}
                />
                <Input
                  label="Country (2-letter)"
                  required
                  maxLength={2}
                  value={newAddress.country}
                  onChange={(e) => setNewAddress({ ...newAddress, country: e.target.value.toUpperCase() })}
                />
                <div style={{ display: "flex", alignItems: "center", gap: 8, alignSelf: "end" }}>
                  <input
                    type="checkbox"
                    id="is_default"
                    checked={newAddress.is_default}
                    onChange={(e) => setNewAddress({ ...newAddress, is_default: e.target.checked })}
                  />
                  <label htmlFor="is_default" style={{ fontSize: "var(--fs-sm)" }}>
                    Set as default
                  </label>
                </div>
                <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", gap: 12 }}>
                  {addresses && addresses.length > 0 && (
                    <Button type="button" variant="ghost" onClick={() => setShowNewAddressForm(false)}>
                      Cancel
                    </Button>
                  )}
                  <Button type="submit" disabled={createAddress.isPending}>
                    {createAddress.isPending ? "Saving…" : "Save address"}
                  </Button>
                </div>
              </motion.form>
            )}

            <div className={styles.actions} style={{ marginTop: 24 }}>
              <Button disabled={!selectedAddressId || startCheckout.isPending} onClick={handleProceedToReview}>
                {startCheckout.isPending ? "Calculating…" : "Continue to review"}
              </Button>
            </div>
          </motion.div>
        )}

        {step === "review" && snapshot && (
          <motion.div key="review" variants={fadeIn} initial="hidden" animate="visible" exit="hidden" className={styles.card}>
            <h2 className={styles.sectionTitle}>Review your order</h2>

            <div className={styles.itemsPreview}>
              {buyNow && buyNowProduct ? (
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span>
                    {buyNow.quantity} × {buyNowProduct.product_name}
                  </span>
                  <span>{formatMoney(Number.parseFloat(buyNowProduct.base_price) * buyNow.quantity)}</span>
                </div>
              ) : (
                cart?.items.map((item) => (
                  <div key={item.cart_item_id} style={{ display: "flex", justifyContent: "space-between" }}>
                    <span>
                      {item.quantity} × {item.product_name}
                    </span>
                    <span>{formatMoney(item.line_subtotal)}</span>
                  </div>
                ))
              )}
            </div>

            <div className={styles.summaryRows}>
              <div className={styles.summaryRow}>
                <span>Gross merchandise value</span>
                <span>{formatMoney(gmv, snapshot.currency)}</span>
              </div>
              <div className={styles.summaryRow}>
                <span>Discount</span>
                <span>−{formatMoney(discount, snapshot.currency)}</span>
              </div>
              <div className={styles.summaryTotal}>
                <span>Total</span>
                <span>{formatMoney(net, snapshot.currency)}</span>
              </div>
            </div>

            <div className={styles.actions}>
              <Button variant="ghost" onClick={() => setStep("address")}>
                Back
              </Button>
              <Button onClick={handleConfirmOrder} disabled={createOrder.isPending}>
                {createOrder.isPending ? "Placing order…" : "Place order"}
              </Button>
            </div>
          </motion.div>
        )}

        {step === "success" && placedOrder && (
          <motion.div key="success" variants={fadeIn} initial="hidden" animate="visible" className={styles.card}>
            <div className={styles.successWrap}>
              <AnimatedCheckmark />
              <h2 className={styles.successTitle}>Order confirmed</h2>
              <p className={styles.successCopy}>
                {formatMoney(placedOrder.total_amount, placedOrder.currency)} · {placedOrder.item_count} item
                {placedOrder.item_count !== 1 ? "s" : ""}
              </p>
              <div className={styles.actions} style={{ justifyContent: "center" }}>
                <Button variant="secondary" onClick={() => navigate("/products")}>
                  Keep shopping
                </Button>
                <Button onClick={() => navigate(`/orders/${placedOrder.order_id}`)}>View order</Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function StepDot({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  const styleClass = active ? styles.stepActive : done ? styles.stepDone : "";
  return (
    <div className={[styles.step, styleClass].join(" ")}>
      <span className={styles.stepDot}>{done ? <Check size={11} /> : ""}</span>
      {label}
    </div>
  );
}
