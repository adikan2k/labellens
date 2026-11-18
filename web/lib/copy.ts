/** Interface wording from docs/DESIGN.md section 4. One place, so every page says it the same way. */

export const WAKING_UP = "Search is waking up. Try again in a few seconds.";
export const NO_MATCH = "No products match. Try a brand name or scan the barcode number.";
export const AI_NOTE = "Written by AI from Open Food Facts data.";
export const AI_CATEGORY_NOTE =
  "Category suggested by AI from the product’s name and ingredients; Open Food Facts gives none.";
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

export const SWAP_RULE =
  "Same category, a better Nutri-Score, and no additive that Open Food Facts flags for high overexposure risk.";
export const SWAPS_UNAVAILABLE = "Swaps are not available right now. Try again in a minute.";

/** Why a product has no swaps, from what the swap rule needs. */
export function noSwapsReason(product: {
  nutriscore_grade: string | null;
  category_main: string | null;
}): string {
  if (!product.category_main || product.category_main === "other") {
    return "This product has no category to compare within.";
  }
  if (!product.nutriscore_grade) {
    return "Open Food Facts has no Nutri-Score for this product, so there is nothing to compare.";
  }
  if (product.nutriscore_grade === "a") {
    return "It already scores Nutri-Score A, so nothing in its category scores better.";
  }
  return "No similar product in this category scores better without a flagged additive.";
}
