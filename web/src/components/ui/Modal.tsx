import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { backdropVariants, scaleIn } from "../../lib/motion";
import { Button } from "./Button";
import styles from "./Modal.module.css";

interface ModalProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  confirmVariant?: "primary" | "danger";
  onConfirm?: () => void;
  onClose: () => void;
  busy?: boolean;
}

export function Modal({
  open,
  title,
  children,
  confirmLabel,
  confirmVariant = "primary",
  onConfirm,
  onClose,
  busy = false,
}: ModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className={styles.backdrop}
          variants={backdropVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          onClick={onClose}
        >
          <motion.div
            className={styles.dialog}
            variants={scaleIn}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className={styles.title}>{title}</h3>
            <div className={styles.body}>{children}</div>
            <div className={styles.actions}>
              <Button variant="ghost" onClick={onClose} disabled={busy}>
                Cancel
              </Button>
              {onConfirm && (
                <Button variant={confirmVariant} onClick={onConfirm} disabled={busy}>
                  {busy ? "Working…" : confirmLabel}
                </Button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
