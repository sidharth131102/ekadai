import { motion } from "framer-motion";
import { ChevronRight, PackageOpen } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useOrders } from "../api/hooks/useOrders";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Skeleton } from "../components/ui/Skeleton";
import { formatDate, formatMoney } from "../lib/format";
import { staggerContainer, staggerItem } from "../lib/motion";
import { usePageView } from "../lib/usePageView";
import styles from "./Orders.module.css";

const PAGE_SIZE = 10;

export default function Orders() {
  usePageView("orders");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useOrders(page, PAGE_SIZE);
  const navigate = useNavigate();

  return (
    <div className={["container", styles.page].join(" ")}>
      <h1 className={styles.heading}>Order history</h1>

      {isLoading && (
        <div className={styles.list}>
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} height={72} radius="12px" />
          ))}
        </div>
      )}

      {!isLoading && (!data || data.items.length === 0) && (
        <div className={styles.empty}>
          <PackageOpen size={36} style={{ opacity: 0.4, marginBottom: 12 }} />
          <p style={{ marginBottom: 16 }}>You haven't placed any orders yet.</p>
          <Button onClick={() => navigate("/products")}>Start shopping</Button>
        </div>
      )}

      {data && data.items.length > 0 && (
        <motion.div className={styles.list} variants={staggerContainer} initial="hidden" animate="visible">
          {data.items.map((order) => (
            <motion.button
              key={order.order_id}
              variants={staggerItem}
              className={styles.row}
              whileHover={{ x: 4 }}
              onClick={() => navigate(`/orders/${order.order_id}`)}
            >
              <div className={styles.rowLeft}>
                <span className={styles.orderId}>Order #{order.order_id.slice(0, 8)}</span>
                <span className={styles.orderMeta}>
                  {formatDate(order.created_at)} · {order.item_count} item{order.item_count !== 1 ? "s" : ""}
                </span>
              </div>
              <div className={styles.rowRight}>
                <Badge tone={order.status === "CONFIRMED" ? "success" : "danger"}>{order.status}</Badge>
                <span className={styles.total}>{formatMoney(order.total_amount, order.currency)}</span>
                <ChevronRight size={18} color="var(--color-ink-faint)" />
              </div>
            </motion.button>
          ))}
        </motion.div>
      )}

      {data && data.total > PAGE_SIZE && (
        <div style={{ display: "flex", justifyContent: "center", gap: 16, marginTop: 24 }}>
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={page * PAGE_SIZE >= data.total}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
