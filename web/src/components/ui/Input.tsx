import { motion } from "framer-motion";
import type { InputHTMLAttributes } from "react";
import { useId } from "react";
import styles from "./Input.module.css";

// motion.input's gesture event handler types collide with the plain HTML ones on these
// specific props — omit before spreading onto motion.input.
type NativeInputProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "onDrag" | "onDragStart" | "onDragEnd" | "onAnimationStart" | "onAnimationEnd" | "onAnimationIteration"
>;

interface InputProps extends NativeInputProps {
  label?: string;
  error?: string;
}

export function Input({ label, error, id, className, ...rest }: InputProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <div className={styles.field}>
      {label && (
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
      )}
      <motion.input
        id={inputId}
        className={[styles.input, error ? styles.error : "", className ?? ""].filter(Boolean).join(" ")}
        animate={error ? { x: [0, -7, 7, -5, 5, 0] } : { x: 0 }}
        transition={{ duration: 0.35 }}
        {...rest}
      />
      {error && <span className={styles.errorText}>{error}</span>}
    </div>
  );
}
