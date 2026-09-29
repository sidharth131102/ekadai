import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { CategoryOut, ProductListParams, ProductListResponse, ProductOut } from "../types";

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: () => apiRequest<CategoryOut[]>("/categories"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useProducts(params: ProductListParams) {
  return useQuery({
    queryKey: ["products", params],
    queryFn: () =>
      apiRequest<ProductListResponse>("/products", {
        query: {
          q: params.q,
          category_id: params.category_id,
          brand: params.brand,
          min_price: params.min_price,
          max_price: params.max_price,
          min_rating: params.min_rating,
          max_rating: params.max_rating,
          availability: params.availability,
          sort: params.sort,
          order: params.order,
          page: params.page,
          page_size: params.page_size,
        },
      }),
    placeholderData: (prev) => prev,
  });
}

export function useProduct(productId: string | undefined) {
  return useQuery({
    queryKey: ["product", productId],
    queryFn: () => apiRequest<ProductOut>(`/products/${productId}`),
    enabled: !!productId,
  });
}
