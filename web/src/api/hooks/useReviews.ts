import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { ReviewCreateRequest, ReviewListResponse } from "../types";

export function useReviews(productId: string | undefined) {
  return useQuery({
    queryKey: ["reviews", productId],
    queryFn: () => apiRequest<ReviewListResponse>(`/products/${productId}/reviews`),
    enabled: !!productId,
  });
}

export function useCreateReview(productId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReviewCreateRequest) =>
      apiRequest(`/products/${productId}/reviews`, { method: "POST", body: payload }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reviews", productId] });
      queryClient.invalidateQueries({ queryKey: ["product", productId] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
  });
}
