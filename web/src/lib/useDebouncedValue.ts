import { useEffect, useState } from "react";

/** Returns `value`, updated only after it's stopped changing for `delayMs`. Used to debounce
 * *event emission* only (search/filter_applied) — the live query/URL state stays instant. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
