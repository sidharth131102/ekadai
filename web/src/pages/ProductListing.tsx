import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useCategories, useProducts } from "../api/hooks/useCatalog";
import { useAddToCart } from "../api/hooks/useCart";
import { useAddToWishlist, useRemoveFromWishlist, useWishlist } from "../api/hooks/useWishlist";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { Button } from "../components/ui/Button";
import { FilterPanel, type ProductFilters } from "../components/product/FilterPanel";
import { ProductGrid } from "../components/product/ProductGrid";
import { trackEvent } from "../lib/analytics";
import { useDebouncedValue } from "../lib/useDebouncedValue";
import { usePageView } from "../lib/usePageView";
import type { ProductOut } from "../api/types";
import { useNavigate } from "react-router-dom";
import styles from "./ProductListing.module.css";

const PAGE_SIZE = 12;

export default function ProductListing() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { isAuthenticated } = useAuth();
  const { showToast } = useToast();
  const navigate = useNavigate();

  const filters: ProductFilters = {
    q: searchParams.get("q") ?? "",
    category_id: searchParams.get("category_id") ?? "",
    min_price: searchParams.get("min_price") ?? "",
    max_price: searchParams.get("max_price") ?? "",
    min_rating: searchParams.get("min_rating") ?? "",
    availability: searchParams.get("availability") === "true",
    sort: (searchParams.get("sort") as ProductFilters["sort"]) ?? "newest",
    order: (searchParams.get("order") as ProductFilters["order"]) ?? "desc",
  };
  const page = Number.parseInt(searchParams.get("page") ?? "1", 10);

  // §30: "category" vs "product_listing" are distinct page_types for the same component,
  // distinguished by whether a category filter is active.
  usePageView(filters.category_id ? "category" : "product_listing", undefined, filters.category_id || undefined);

  function updateFilters(next: Partial<ProductFilters>) {
    const merged = { ...filters, ...next };
    const params = new URLSearchParams();
    if (merged.q) params.set("q", merged.q);
    if (merged.category_id) params.set("category_id", merged.category_id);
    if (merged.min_price) params.set("min_price", merged.min_price);
    if (merged.max_price) params.set("max_price", merged.max_price);
    if (merged.min_rating) params.set("min_rating", merged.min_rating);
    if (merged.availability) params.set("availability", "true");
    params.set("sort", merged.sort);
    params.set("order", merged.order);
    // any filter change resets pagination
    setSearchParams(params);
  }

  function goToPage(next: number) {
    const params = new URLSearchParams(searchParams);
    params.set("page", String(next));
    setSearchParams(params);
  }

  const { data: categories } = useCategories();
  const { data, isLoading } = useProducts({
    q: filters.q || undefined,
    category_id: filters.category_id || undefined,
    min_price: filters.min_price || undefined,
    max_price: filters.max_price || undefined,
    min_rating: filters.min_rating ? Number(filters.min_rating) : undefined,
    availability: filters.availability || undefined,
    sort: filters.sort,
    order: filters.order,
    page,
    page_size: PAGE_SIZE,
  });
  const { data: wishlist } = useWishlist();
  const addToCart = useAddToCart();
  const addToWishlist = useAddToWishlist();
  const removeFromWishlist = useRemoveFromWishlist();

  // §30: "Do NOT emit an event for every keystroke" — event emission is debounced
  // separately from the live query above, which stays instant for good UX.
  const debouncedQuery = useDebouncedValue(filters.q, 600);
  useEffect(() => {
    if (debouncedQuery) {
      trackEvent("search", { search_query: debouncedQuery, search_result_count: data?.total ?? 0 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery]);

  // category_id/availability are discrete control changes (select/toggle) -- fire
  // immediately; price is free-text, debounced like search.
  const debouncedMinPrice = useDebouncedValue(filters.min_price, 500);
  const debouncedMaxPrice = useDebouncedValue(filters.max_price, 500);
  useEffect(() => {
    const activeFilters: Record<string, unknown>[] = [];
    if (filters.category_id) {
      activeFilters.push({
        filter_type: "category",
        filter_value_string: null,
        filter_value_min: null,
        filter_value_max: null,
        filter_value_boolean: null,
        category_id: filters.category_id,
      });
    }
    if (debouncedMinPrice || debouncedMaxPrice) {
      activeFilters.push({
        filter_type: "price",
        filter_value_string: null,
        filter_value_min: debouncedMinPrice ? Number(debouncedMinPrice) : null,
        filter_value_max: debouncedMaxPrice ? Number(debouncedMaxPrice) : null,
        filter_value_boolean: null,
        category_id: null,
      });
    }
    if (filters.availability) {
      activeFilters.push({
        filter_type: "availability",
        filter_value_string: null,
        filter_value_min: null,
        filter_value_max: null,
        filter_value_boolean: true,
        category_id: null,
      });
    }
    if (filters.min_rating) {
      activeFilters.push({
        filter_type: "rating",
        filter_value_string: null,
        filter_value_min: Number(filters.min_rating),
        filter_value_max: 5,
        filter_value_boolean: null,
        category_id: null,
      });
    }
    if (activeFilters.length > 0) {
      trackEvent("filter_applied", { filters: activeFilters });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.category_id, filters.availability, filters.min_rating, debouncedMinPrice, debouncedMaxPrice]);

  // Sort has a default (newest/desc) on first load -- that's not a user choice, so skip
  // the initial mount and only fire on an actual change.
  const isFirstSortRender = useRef(true);
  useEffect(() => {
    if (isFirstSortRender.current) {
      isFirstSortRender.current = false;
      return;
    }
    trackEvent("sort_applied", { sort_field: filters.sort, sort_direction: filters.order });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.sort, filters.order]);

  const wishlistedIds = new Set((wishlist?.items ?? []).map((i) => i.product_id));
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  function handleAddToCart(product: ProductOut) {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    addToCart.mutate({ product_id: product.product_id, quantity: 1 });
    showToast(`Added ${product.product_name} to your bag`, "success");
  }

  function handleToggleWishlist(product: ProductOut) {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    const existing = wishlist?.items.find((i) => i.product_id === product.product_id);
    if (existing) {
      removeFromWishlist.mutate(existing.wishlist_item_id);
    } else {
      addToWishlist.mutate(product.product_id);
      showToast(`Saved ${product.product_name} to your wishlist`, "success");
    }
  }

  return (
    <div className={["container", styles.page].join(" ")}>
      <h1 className={styles.heading}>Shop the catalog</h1>
      {data && <p className={styles.resultCount}>{data.total} products</p>}

      <FilterPanel categories={categories} filters={filters} onChange={updateFilters} />

      <ProductGrid
        products={data?.items}
        isLoading={isLoading}
        wishlistedIds={wishlistedIds}
        onToggleWishlist={handleToggleWishlist}
        onAddToCart={handleAddToCart}
        emptyMessage="Try a different search or clear your filters."
      />

      {data && totalPages > 1 && (
        <div className={styles.pagination}>
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => goToPage(page - 1)}>
            Previous
          </Button>
          <span className={styles.pageLabel}>
            Page {page} of {totalPages}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => goToPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
