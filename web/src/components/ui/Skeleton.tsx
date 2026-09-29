import type { CSSProperties } from "react";
import styles from "./Skeleton.module.css";

export function Skeleton({ width = "100%", height = "1rem", radius, className }: {
  width?: string | number;
  height?: string | number;
  radius?: string;
  className?: string;
}) {
  const style: CSSProperties = { width, height, borderRadius: radius };
  return <div className={[styles.skeleton, className ?? ""].filter(Boolean).join(" ")} style={style} />;
}
