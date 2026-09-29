const currencyFormatters = new Map<string, Intl.NumberFormat>();

// Locale follows the currency being displayed (en-IN groups digits as
// lakhs/crores — ₹1,29,900 — which is what an INR price should actually look like), not a
// single hardcoded locale.
const LOCALE_BY_CURRENCY: Record<string, string> = { INR: "en-IN", USD: "en-US" };

export function formatMoney(value: string | number, currency = "INR"): string {
  let formatter = currencyFormatters.get(currency);
  if (!formatter) {
    formatter = new Intl.NumberFormat(LOCALE_BY_CURRENCY[currency] ?? "en-US", {
      style: "currency",
      currency,
    });
    currencyFormatters.set(currency, formatter);
  }
  return formatter.format(typeof value === "string" ? Number.parseFloat(value) : value);
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
