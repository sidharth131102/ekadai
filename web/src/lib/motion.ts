import type { Transition, Variants } from "framer-motion";

// Shared spring — the "buttery" feel, reused everywhere instead of one-off tunings.
export const buttery: Transition = { type: "spring", stiffness: 320, damping: 32, mass: 0.9 };
export const butteryGentle: Transition = { type: "spring", stiffness: 220, damping: 28, mass: 1 };

export const pageVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { ...buttery, delay: 0.03 } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.18, ease: "easeIn" } },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.055, delayChildren: 0.04 },
  },
};

export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: buttery },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.4, ease: "easeOut" } },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.94 },
  visible: { opacity: 1, scale: 1, transition: buttery },
  exit: { opacity: 0, scale: 0.96, transition: { duration: 0.15 } },
};

export const drawerVariants: Variants = {
  hidden: { x: "100%" },
  visible: { x: 0, transition: buttery },
  exit: { x: "100%", transition: { ...buttery, stiffness: 260 } },
};

export const backdropVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.25 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
};

export const toastVariants: Variants = {
  hidden: { opacity: 0, y: 24, scale: 0.95 },
  visible: { opacity: 1, y: 0, scale: 1, transition: buttery },
  exit: { opacity: 0, x: -60, transition: { duration: 0.2, ease: "easeIn" } },
};

export const cardHover = {
  whileHover: { y: -6, transition: butteryGentle },
  whileTap: { scale: 0.98 },
};

export const pressable = {
  whileTap: { scale: 0.96 },
};
