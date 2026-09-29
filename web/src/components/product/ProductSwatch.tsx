import { motion } from "framer-motion";
import {
  BookOpen,
  Cpu,
  Dumbbell,
  Package,
  Shirt,
  Sparkles,
  UtensilsCrossed,
  Watch,
} from "lucide-react";
import { swatchGradient, swatchIconIndex } from "../../lib/swatch";

const ICONS = [Package, Shirt, Sparkles, Dumbbell, BookOpen, Watch, Cpu, UtensilsCrossed];

export function ProductSwatch({
  seed,
  layoutId,
  iconSize = 48,
}: {
  seed: string;
  layoutId?: string;
  iconSize?: number;
}) {
  const Icon = ICONS[swatchIconIndex(seed)];
  return (
    <motion.div
      layoutId={layoutId}
      style={{
        background: swatchGradient(seed),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: "100%",
        height: "100%",
        borderRadius: "inherit",
      }}
    >
      <Icon size={iconSize} strokeWidth={1.1} color="rgba(253, 251, 246, 0.88)" />
    </motion.div>
  );
}
