import { motion } from "framer-motion";
import { ArrowLeft, Check, PackageCheck, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCancelOrder, useOrder } from "../api/hooks/useOrders";
import { ApiError } from "../api/client";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Skeleton } from "../components/ui/Skeleton";
import { useToast } from "../context/ToastContext";
import { trackEvent } from "../lib/analytics";
import { fadeIn } from "../lib/motion";
import { formatDateTime, formatMoney } from "../lib/format";
import { usePageView } from "../lib/usePageView";
import styles from "./OrderDetail.module.css";

export default function OrderDetail() {
  usePageView("orders");
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { data: order, isLoading } = useOrder(orderId);
  const cancelOrder = useCancelOrder();
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => {
    if (order) trackEvent("order_viewed", { order_id: order.order_id, page_context: "order_details" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order?.order_id]);

  async function handleCancel() {
    if (!order) return;
    try {
      await cancelOrder.mutateAsync(order.order_id);
      showToast("Order cancelled.", "success");
      setConfirmOpen(false);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not cancel order.", "error");
    }
  }

  if (isLoading || !order) {
    return (
      <div className={["container", styles.page].join(" ")}>
        <div style={{ marginBottom: 24 }}>
          <Skeleton height={24} width="30%" />
        </div>
        <Skeleton height={160} radius="16px" />
      </div>
    );
  }

  const isCancelled = order.status === "CANCELLED";

  return (
    <div className={["container", styles.page].join(" ")}>
      <button className={styles.back} onClick={() => navigate("/orders")}>
        <ArrowLeft size={15} /> All orders
      </button>

      <motion.div variants={fadeIn} initial="hidden" animate="visible">
        <div className={styles.headRow}>
          <h1 className={styles.heading}>Order #{order.order_id.slice(0, 8)}</h1>
          <Badge tone={isCancelled ? "danger" : "success"}>{order.status}</Badge>
        </div>

        <div className={styles.timeline}>
          <TimelineStep
            icon={<Check size={14} />}
            label="Placed"
            time={formatDateTime(order.created_at)}
            active
          />
          <TimelineStep
            icon={<PackageCheck size={14} />}
            label="Confirmed"
            time={formatDateTime(order.confirmed_at)}
            active
          />
          <TimelineStep
            icon={<X size={14} />}
            label={isCancelled ? "Cancelled" : "Active"}
            time={order.cancelled_at ? formatDateTime(order.cancelled_at) : undefined}
            active={isCancelled}
            danger={isCancelled}
            last
          />
        </div>

        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Items</h2>
          {order.items.map((item) => (
            <div key={item.order_item_id} className={styles.itemRow}>
              <span>
                {item.quantity} × {item.product_name}
              </span>
              <span>{formatMoney(item.line_revenue, item.currency)}</span>
            </div>
          ))}
          <div className={styles.totalsRow}>
            <span>Total</span>
            <span>{formatMoney(order.total_amount, order.currency)}</span>
          </div>
        </div>

        <div className={styles.card}>
          <h2 className={styles.cardTitle}>Shipping address</h2>
          <p className={styles.addressText}>
            {order.shipping_address_line1}
            {order.shipping_address_line2 ? `, ${order.shipping_address_line2}` : ""}
            <br />
            {order.shipping_city}, {order.shipping_state} {order.shipping_postal_code}
            <br />
            {order.shipping_country}
          </p>
        </div>

        {!isCancelled && (
          <Button variant="danger" onClick={() => setConfirmOpen(true)}>
            Cancel order
          </Button>
        )}
      </motion.div>

      <Modal
        open={confirmOpen}
        title="Cancel this order?"
        confirmLabel="Cancel order"
        confirmVariant="danger"
        onConfirm={handleCancel}
        onClose={() => setConfirmOpen(false)}
        busy={cancelOrder.isPending}
      >
        This can't be undone. Your order for {formatMoney(order.total_amount, order.currency)} will be
        cancelled.
      </Modal>
    </div>
  );
}

function TimelineStep({
  icon,
  label,
  time,
  active,
  danger,
  last,
}: {
  icon: ReactNode;
  label: string;
  time?: string;
  active: boolean;
  danger?: boolean;
  last?: boolean;
}) {
  return (
    <div className={styles.timelineStep}>
      {!last && <div className={styles.timelineLine} />}
      <div
        className={[
          styles.timelineDot,
          active ? (danger ? styles.timelineDotDanger : styles.timelineDotActive) : "",
        ].join(" ")}
      >
        {icon}
      </div>
      <span className={styles.timelineLabel}>{label}</span>
      {time && <span className={styles.timelineTime}>{time}</span>}
    </div>
  );
}
