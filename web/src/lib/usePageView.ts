import { useEffect } from "react";
import { trackEvent } from "./analytics";

// §30's page_type enum — Login/Register aren't in it, so those pages intentionally don't
// call this hook.
export type PageType =
  | "home"
  | "category"
  | "product_listing"
  | "product_detail"
  | "cart"
  | "checkout"
  | "orders"
  | "profile"
  | "wishlist";

export function usePageView(pageType: PageType, productId?: string, categoryId?: string): void {
  useEffect(() => {
    trackEvent("page_view", {
      page_type: pageType,
      product_id: productId ?? null,
      category_id: categoryId ?? null,
    });
    // Intentionally re-fires if productId/categoryId change even without a remount —
    // that's still a new page view (e.g. a different product's detail page).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageType, productId, categoryId]);
}
