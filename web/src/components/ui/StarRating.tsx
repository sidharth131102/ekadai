import { Star } from "lucide-react";
import styles from "./StarRating.module.css";

interface StarRatingProps {
  rating: number | null;
  count?: number;
  size?: number;
  showCount?: boolean;
}

export function StarRating({ rating, count = 0, size = 14, showCount = true }: StarRatingProps) {
  if (rating === null) {
    return <span className={styles.empty}>No reviews yet</span>;
  }

  return (
    <span className={styles.wrap}>
      <span className={styles.stars}>
        {Array.from({ length: 5 }).map((_, i) => {
          const filled = i < Math.round(rating);
          return (
            <Star
              key={i}
              size={size}
              fill={filled ? "var(--color-accent)" : "none"}
              color={filled ? "var(--color-accent)" : "var(--color-border-strong)"}
              strokeWidth={1.5}
            />
          );
        })}
      </span>
      {showCount && (
        <span className={styles.count}>
          {rating.toFixed(1)} ({count})
        </span>
      )}
    </span>
  );
}
