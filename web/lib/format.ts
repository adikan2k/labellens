/** Number and label formatting shared by the product page and the dashboard. */

export function formatEnergy(kcal: number): string {
  return `${Math.round(kcal)} kcal`;
}

/** Grams as a label prints them: "0 g", "<0.1 g", "2.5 g", "12 g". */
export function formatGrams(grams: number): string {
  if (grams === 0) return "0 g";
  if (grams < 0.05) return "<0.1 g";
  if (grams < 10) return `${Number(grams.toFixed(1))} g`;
  return `${Math.round(grams)} g`;
}

export const NOVA_LABELS: Record<number, string> = {
  1: "Unprocessed or minimally processed",
  2: "Processed culinary ingredients",
  3: "Processed foods",
  4: "Ultra-processed foods",
};

export function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

export function formatShare(part: number, whole: number): string {
  if (!whole) return "0%";
  const share = (100 * part) / whole;
  return share > 0 && share < 1 ? "<1%" : `${Math.round(share)}%`;
}
