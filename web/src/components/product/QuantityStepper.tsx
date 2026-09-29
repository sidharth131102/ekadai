import { Minus, Plus } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import styles from "./QuantityStepper.module.css";

interface QuantityStepperProps {
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
}

export function QuantityStepper({ value, onChange, min = 1, max = 99 }: QuantityStepperProps) {
  return (
    <div className={styles.stepper}>
      <motion.button
        type="button"
        className={styles.stepButton}
        whileTap={{ scale: 0.85 }}
        disabled={value <= min}
        onClick={() => onChange(Math.max(min, value - 1))}
        aria-label="Decrease quantity"
      >
        <Minus size={15} />
      </motion.button>
      <span className={styles.value}>
        <AnimatePresence mode="popLayout" initial={false}>
          <motion.span
            key={value}
            initial={{ y: -8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 8, opacity: 0 }}
            transition={{ duration: 0.16 }}
            style={{ display: "inline-block" }}
          >
            {value}
          </motion.span>
        </AnimatePresence>
      </span>
      <motion.button
        type="button"
        className={styles.stepButton}
        whileTap={{ scale: 0.85 }}
        disabled={value >= max}
        onClick={() => onChange(Math.min(max, value + 1))}
        aria-label="Increase quantity"
      >
        <Plus size={15} />
      </motion.button>
    </div>
  );
}
