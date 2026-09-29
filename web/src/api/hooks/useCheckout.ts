import { useMutation } from "@tanstack/react-query";
import { apiRequest } from "../client";
import type { BuyNowLine, CheckoutSnapshotOut } from "../types";

export function useStartCheckout() {
  return useMutation({
    mutationFn: (buyNow?: BuyNowLine) =>
      apiRequest<CheckoutSnapshotOut>("/checkout/start", {
        method: "POST",
        body: buyNow ? { buy_now: buyNow } : undefined,
      }),
  });
}
