// Fire-and-forget client event tracking. POSTs to the Phase 3b ingestion endpoint
// (app/routers/events.py) — never blocks the UI, never surfaces an error to the caller.
// The backend fills in event_id/context/device; this only sends what genuinely originates
// in the browser: which event, when it happened, and its specific payload.

import { apiRequest } from "../api/client";

export type ClientEventType =
  | "page_view"
  | "search"
  | "filter_applied"
  | "sort_applied"
  | "product_view"
  | "wishlist_view"
  | "order_viewed"
  | "buy_now_clicked";

export function trackEvent(eventType: ClientEventType, payload: Record<string, unknown>): void {
  apiRequest("/events", {
    method: "POST",
    body: { event_type: eventType, event_timestamp: Date.now(), payload },
  }).catch(() => {
    /* telemetry must never break the UI */
  });
}
