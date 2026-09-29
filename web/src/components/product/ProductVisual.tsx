import { motion } from "framer-motion";
import { ProductSwatch } from "./ProductSwatch";

interface ProductVisualProps {
  productId: string;
  imageUrl: string | null;
  layoutId?: string;
  iconSize?: number;
}

/** Real product photo when available, falling back to the Phase 2b swatch design
 * otherwise — products carry no guaranteed image in the schema (image_url is nullable),
 * so this fallback stays meaningful rather than showing a broken-image icon. */
export function ProductVisual({ productId, imageUrl, layoutId, iconSize }: ProductVisualProps) {
  if (imageUrl) {
    return (
      <motion.img
        layoutId={layoutId}
        src={imageUrl}
        alt=""
        loading="lazy"
        style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }}
      />
    );
  }
  return <ProductSwatch seed={productId} layoutId={layoutId} iconSize={iconSize} />;
}
