import { motion } from "framer-motion";
import { Star } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useCreateReview } from "../../api/hooks/useReviews";
import { useToast } from "../../context/ToastContext";
import { Button } from "../ui/Button";
import { Input } from "../ui/Input";
import styles from "./ReviewForm.module.css";

export function ReviewForm({ productId }: { productId: string }) {
  const [rating, setRating] = useState(0);
  const [hoverRating, setHoverRating] = useState(0);
  const [reviewerName, setReviewerName] = useState("");
  const [reviewText, setReviewText] = useState("");
  const createReview = useCreateReview(productId);
  const { showToast } = useToast();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (rating === 0) {
      showToast("Pick a star rating first.", "error");
      return;
    }
    try {
      await createReview.mutateAsync({
        reviewer_name: reviewerName,
        rating,
        review_text: reviewText || null,
      });
      showToast("Thanks for the review!", "success");
      setRating(0);
      setReviewerName("");
      setReviewText("");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not submit review.", "error");
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <div>
        <span style={{ fontSize: "var(--fs-xs)", fontWeight: 600, color: "var(--color-ink-muted)" }}>
          Your rating
        </span>
        <div className={styles.starPicker}>
          {Array.from({ length: 5 }).map((_, i) => {
            const value = i + 1;
            const filled = value <= (hoverRating || rating);
            return (
              <motion.button
                key={value}
                type="button"
                className={styles.starButton}
                whileTap={{ scale: 0.85 }}
                onMouseEnter={() => setHoverRating(value)}
                onMouseLeave={() => setHoverRating(0)}
                onClick={() => setRating(value)}
                aria-label={`${value} star${value > 1 ? "s" : ""}`}
              >
                <Star
                  size={22}
                  fill={filled ? "var(--color-accent)" : "none"}
                  color={filled ? "var(--color-accent)" : "var(--color-border-strong)"}
                  strokeWidth={1.5}
                />
              </motion.button>
            );
          })}
        </div>
      </div>

      <Input
        label="Your name"
        required
        maxLength={120}
        value={reviewerName}
        onChange={(e) => setReviewerName(e.target.value)}
        placeholder="How should this appear on your review?"
      />

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
        <span style={{ fontSize: "var(--fs-xs)", fontWeight: 600, color: "var(--color-ink-muted)" }}>
          Review (optional)
        </span>
        <textarea
          className={styles.textarea}
          maxLength={4000}
          value={reviewText}
          onChange={(e) => setReviewText(e.target.value)}
          placeholder="What did you think?"
        />
      </div>

      <Button type="submit" disabled={createReview.isPending}>
        {createReview.isPending ? "Submitting…" : "Submit review"}
      </Button>
    </form>
  );
}
