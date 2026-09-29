import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { WishlistOut } from "../types";
import { useAuth } from "../../context/AuthContext";

const WISHLIST_KEY = ["wishlist"];

export function useWishlist() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: WISHLIST_KEY,
    queryFn: () => apiRequest<WishlistOut>("/wishlist"),
    enabled: isAuthenticated,
  });
}

export function useAddToWishlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) =>
      apiRequest<WishlistOut>("/wishlist/items", { method: "POST", body: { product_id: productId } }),
    onSuccess: (data) => queryClient.setQueryData(WISHLIST_KEY, data),
  });
}

export function useRemoveFromWishlist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (wishlistItemId: string) =>
      apiRequest<WishlistOut>(`/wishlist/items/${wishlistItemId}`, { method: "DELETE" }),
    onSuccess: (data) => queryClient.setQueryData(WISHLIST_KEY, data),
  });
}
