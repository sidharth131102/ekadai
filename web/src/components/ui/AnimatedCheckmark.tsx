import { motion } from "framer-motion";

export function AnimatedCheckmark({ size = 72 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 72 72" fill="none" style={{ margin: "0 auto" }}>
      <motion.circle
        cx="36"
        cy="36"
        r="33"
        stroke="var(--color-success)"
        strokeWidth="3"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={{ pathLength: 1, opacity: 1 }}
        transition={{ duration: 0.6, ease: "easeInOut" }}
      />
      <motion.path
        d="M22 37.5L31.5 47L50.5 26"
        stroke="var(--color-success)"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.45, ease: "easeOut", delay: 0.5 }}
      />
    </svg>
  );
}
