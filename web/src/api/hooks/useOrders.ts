import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { OrderCreateRequest, OrderListResponse, OrderOut } from "../types";
import { useAuth } from "../../context/AuthContext";

export function useOrders(page = 1, pageSize = 20) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ["orders", page, pageSize],
    queryFn: () =>
      apiRequest<OrderListResponse>("/orders", { query: { page, page_size: pageSize } }),
    enabled: isAuthenticated,
  });
}

export function useOrder(orderId: string | undefined) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: () => apiRequest<OrderOut>(`/orders/${orderId}`),
    enabled: !!orderId,
  });
}

export function useCreateOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: OrderCreateRequest) => apiRequest<OrderOut>("/orders", { method: "POST", body: payload }),
    onSuccess: (order) => {
      queryClient.setQueryData(["order", order.order_id], order);
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["cart"] });
    },
  });
}

export function useCancelOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) => apiRequest<OrderOut>(`/orders/${orderId}/cancel`, { method: "POST" }),
    onSuccess: (order) => {
      queryClient.setQueryData(["order", order.order_id], order);
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}
