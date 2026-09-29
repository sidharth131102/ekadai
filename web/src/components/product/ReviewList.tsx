import { motion } from "framer-motion";
import type { ReviewOut } from "../../api/types";
import { formatDate } from "../../lib/format";
import { staggerContainer, staggerItem } from "../../lib/motion";
import { Badge } from "../ui/Badge";
import { StarRating } from "../ui/StarRating";
import styles from "./ReviewList.module.css";

export function ReviewList({ reviews }: { reviews: ReviewOut[] }) {
  if (reviews.length === 0) {
    return <p className={styles.empty}>No reviews yet — be the first to write one.</p>;
  }

  return (
    <motion.div className={styles.list} variants={staggerContainer} initial="hidden" animate="visible">
      {reviews.map((review) => (
        <motion.div key={review.review_id} variants={staggerItem} className={styles.review}>
          <div className={styles.reviewHead}>
            <span className={styles.reviewerName}>
              {review.reviewer_name} {review.is_own && <Badge tone="accent">You</Badge>}
            </span>
            <span className={styles.reviewDate}>{formatDate(review.created_at)}</span>
          </div>
          <StarRating rating={review.rating} showCount={false} size={13} />
          {review.review_text && <p className={styles.reviewText}>{review.review_text}</p>}
        </motion.div>
      ))}
    </motion.div>
  );
}
