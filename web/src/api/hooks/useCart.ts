import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { CartOut } from "../types";
import { useAuth } from "../../context/AuthContext";

const CART_KEY = ["cart"];

export function useCart() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: CART_KEY,
    queryFn: () => apiRequest<CartOut>("/cart"),
    enabled: isAuthenticated,
  });
}

export function useAddToCart() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { product_id: string; quantity: number }) =>
      apiRequest<CartOut>("/cart/items", { method: "POST", body: payload }),
    onSuccess: (data) => queryClient.setQueryData(CART_KEY, data),
  });
}

export function useUpdateCartItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ cartItemId, quantity }: { cartItemId: string; quantity: number }) =>
      apiRequest<CartOut>(`/cart/items/${cartItemId}`, { method: "PATCH", body: { quantity } }),
    onSuccess: (data) => queryClient.setQueryData(CART_KEY, data),
  });
}

export function useRemoveCartItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cartItemId: string) => apiRequest<CartOut>(`/cart/items/${cartItemId}`, { method: "DELETE" }),
    onSuccess: (data) => queryClient.setQueryData(CART_KEY, data),
  });
}
