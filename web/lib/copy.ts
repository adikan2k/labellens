/** Interface wording from docs/DESIGN.md section 4. One place, so every page says it the same way. */

export const WAKING_UP = "Search is waking up. Try again in a few seconds.";
export const NO_MATCH = "No products match. Try a brand name or scan the barcode number.";
export const AI_NOTE = "Written by AI from Open Food Facts data.";
export const ATTRIBUTION = "Contains data from Open Food Facts, available under the Open Database License.";

/** "Open Food Facts has no sugar or fiber value for this product." */
export function missingValues(names: string[]): string | null {
  if (names.length === 0) return null;
  const list =
    names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return `Open Food Facts has no ${list} value for this product.`;
}
