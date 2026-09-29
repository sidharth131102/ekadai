import { AnimatePresence, motion } from "framer-motion";
import { useToast } from "../../context/ToastContext";
import { toastVariants } from "../../lib/motion";
import styles from "./ToastStack.module.css";

export function ToastStack() {
  const { toasts, dismissToast } = useToast();

  return (
    <div className={styles.stack}>
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            layout
            variants={toastVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className={[styles.toast, styles[toast.variant] ?? ""].filter(Boolean).join(" ")}
            onClick={() => dismissToast(toast.id)}
            role="status"
          >
            {toast.message}
            <motion.span
              className={styles.progress}
              initial={{ width: "100%" }}
              animate={{ width: "0%" }}
              transition={{ duration: toast.duration / 1000, ease: "linear" }}
            />
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
