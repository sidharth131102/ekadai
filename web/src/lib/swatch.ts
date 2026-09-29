// Products carry no image_url in the schema (spec never adds one). Rather than broken-image
// icons, render a deterministic color-blocked "catalog swatch" per product — fits the
// editorial print-catalog aesthetic (many real catalogs swatch un-photographed items) and
// never fabricates data, just a visual treatment.

const GRADIENTS = [
  "linear-gradient(135deg, #C1481D 0%, #E08A4F 100%)",
  "linear-gradient(135deg, #4C6B4F 0%, #8FA888 100%)",
  "linear-gradient(135deg, #6B5F4F 0%, #A8927A 100%)",
  "linear-gradient(135deg, #862F10 0%, #C1481D 100%)",
  "linear-gradient(135deg, #2E4A6B 0%, #6E8FAE 100%)",
  "linear-gradient(135deg, #8A6D3B 0%, #D4A85E 100%)",
  "linear-gradient(135deg, #5C4A6B 0%, #9C82AE 100%)",
];

function hashString(input: string): number {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    hash = (hash << 5) - hash + input.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function swatchGradient(seed: string): string {
  return GRADIENTS[hashString(seed) % GRADIENTS.length];
}

// Decorative only (not asserting real category data) — deterministic per product so a
// given item always renders the same icon across renders/pages.
export const SWATCH_ICON_NAMES = [
  "package",
  "shirt",
  "sparkles",
  "dumbbell",
  "book-open",
  "watch",
  "cpu",
  "utensils-crossed",
] as const;

export function swatchIconIndex(seed: string): number {
  return hashString(seed + "-icon") % SWATCH_ICON_NAMES.length;
}
