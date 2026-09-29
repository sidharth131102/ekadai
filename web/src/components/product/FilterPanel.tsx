import { Search } from "lucide-react";
import { motion } from "framer-motion";
import type { CategoryOut, ProductSortField, SortOrder } from "../../api/types";
import styles from "./FilterPanel.module.css";

export interface ProductFilters {
  q: string;
  category_id: string;
  min_price: string;
  max_price: string;
  min_rating: string;
  availability: boolean;
  sort: ProductSortField;
  order: SortOrder;
}

interface FilterPanelProps {
  categories: CategoryOut[] | undefined;
  filters: ProductFilters;
  onChange: (next: Partial<ProductFilters>) => void;
}

const SORT_OPTIONS: { value: ProductSortField; label: string }[] = [
  { value: "newest", label: "Newest" },
  { value: "price", label: "Price" },
  { value: "rating", label: "Rating" },
  { value: "popularity", label: "Popularity" },
];

export function FilterPanel({ categories, filters, onChange }: FilterPanelProps) {
  return (
    <div className={styles.panel}>
      <div className={styles.searchWrap}>
        <span className={styles.fieldLabel}>Search</span>
        <div style={{ position: "relative", marginTop: 4 }}>
          <Search size={16} className={styles.searchIcon} />
          <input
            className={[styles.select, styles.searchInput].join(" ")}
            style={{ width: "100%" }}
            placeholder="Search products or brands…"
            value={filters.q}
            onChange={(e) => onChange({ q: e.target.value })}
          />
        </div>
      </div>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Category</span>
        <select
          className={styles.select}
          value={filters.category_id}
          onChange={(e) => onChange({ category_id: e.target.value })}
        >
          <option value="">All categories</option>
          {categories?.map((c) => (
            <option key={c.category_id} value={c.category_id}>
              {c.category_name}
            </option>
          ))}
        </select>
      </label>

      <div className={styles.field}>
        <span className={styles.fieldLabel}>Price</span>
        <div className={styles.priceRow}>
          <input
            className={styles.priceInput}
            type="number"
            min={0}
            placeholder="Min"
            value={filters.min_price}
            onChange={(e) => onChange({ min_price: e.target.value })}
          />
          <input
            className={styles.priceInput}
            type="number"
            min={0}
            placeholder="Max"
            value={filters.max_price}
            onChange={(e) => onChange({ max_price: e.target.value })}
          />
        </div>
      </div>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Rating</span>
        <select
          className={styles.select}
          value={filters.min_rating}
          onChange={(e) => onChange({ min_rating: e.target.value })}
        >
          <option value="">Any rating</option>
          <option value="4">4+ stars</option>
          <option value="3">3+ stars</option>
          <option value="2">2+ stars</option>
        </select>
      </label>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Sort by</span>
        <select
          className={styles.select}
          value={filters.sort}
          onChange={(e) => onChange({ sort: e.target.value as ProductSortField })}
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Direction</span>
        <select
          className={styles.select}
          value={filters.order}
          onChange={(e) => onChange({ order: e.target.value as SortOrder })}
        >
          <option value="desc">Desc</option>
          <option value="asc">Asc</option>
        </select>
      </label>

      <motion.button
        type="button"
        className={[styles.chip, filters.availability ? styles.chipActive : ""].join(" ")}
        whileTap={{ scale: 0.94 }}
        onClick={() => onChange({ availability: !filters.availability })}
      >
        In stock only
      </motion.button>
    </div>
  );
}
