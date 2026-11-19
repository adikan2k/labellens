/**
 * My basket (DESIGN.md, "My basket"): barcodes kept in this browser only, and the facts about
 * them taken together. No account, no server: the summary is computed here from the same
 * product data every page shows.
 */
import type { Additive, NutriscoreGrade, Product } from "./api";
import { nutrientFlags, NUTRIENT_NAMES, type FlaggedNutrient } from "./thresholds";

export const BASKET_KEY = "labellens.basket.v1";
export const MAX_ITEMS = 30;
export const CHANGED = "labellens:basket";

/** Barcodes from a stored or shared list: digits only, no repeats, at most MAX_ITEMS. */
export function cleanCodes(codes: unknown): string[] {
  if (!Array.isArray(codes)) return [];
  const out: string[] = [];
  for (const code of codes) {
    if (typeof code === "string" && /^\d{1,32}$/.test(code) && !out.includes(code)) out.push(code);
    if (out.length === MAX_ITEMS) break;
  }
  return out;
}

export function readBasket(storage: Storage | undefined = globalThis.localStorage): string[] {
  try {
    return cleanCodes(JSON.parse(storage?.getItem(BASKET_KEY) ?? "[]"));
  } catch {
    return [];
  }
}

export function writeBasket(
  codes: string[],
  storage: Storage | undefined = globalThis.localStorage,
): string[] {
  const clean = cleanCodes(codes);
  try {
    storage?.setItem(BASKET_KEY, JSON.stringify(clean));
  } catch {
    // Storage full or blocked (private browsing): the basket lasts for this page only.
  }
  globalThis.dispatchEvent?.(new Event(CHANGED));
  return clean;
}

export const addToBasket = (code: string) => writeBasket([...readBasket(), code]);
export const removeFromBasket = (code: string) => writeBasket(readBasket().filter((c) => c !== code));
/** Put `next` where `previous` was, keeping the order. */
export const replaceInBasket = (previous: string, next: string) =>
  writeBasket(readBasket().map((c) => (c === previous ? next : c)));

/** The share link's query: barcodes only. */
export function shareHref(codes: string[]): string {
  return `/basket?codes=${cleanCodes(codes).join(",")}`;
}

export function parseShared(raw: string | null): string[] | null {
  if (raw === null) return null;
  return cleanCodes(raw.split(",").map((c) => c.trim()));
}

// --- The summary --------------------------------------------------------------------------

export type BasketAdditive = { additive: Additive; products: string[] };

export type BasketSummary = {
  count: number;
  grades: Record<NutriscoreGrade, number>;
  ungraded: number;
  ultraProcessed: number;
  noNova: number;
  high: { nutrient: FlaggedNutrient; name: string; count: number }[];
  additives: BasketAdditive[];
  flaggedAdditives: number;
};

/** The facts about the products together: counts, never a score. */
export function summarise(products: Product[]): BasketSummary {
  const grades: Record<NutriscoreGrade, number> = { a: 0, b: 0, c: 0, d: 0, e: 0 };
  const high = new Map<FlaggedNutrient, number>();
  const additives = new Map<string, BasketAdditive>();
  let ungraded = 0;
  let ultraProcessed = 0;
  let noNova = 0;
  for (const product of products) {
    if (product.nutriscore_grade) grades[product.nutriscore_grade] += 1;
    else ungraded += 1;
    if (product.nova_group === 4) ultraProcessed += 1;
    else if (product.nova_group === null) noNova += 1;
    for (const flag of nutrientFlags(product.nutrition, product.category_main)) {
      if (flag.level === "high") high.set(flag.nutrient, (high.get(flag.nutrient) ?? 0) + 1);
    }
    for (const additive of product.additives) {
      const entry = additives.get(additive.additive_id) ?? { additive, products: [] };
      entry.products.push(product.code);
      additives.set(additive.additive_id, entry);
    }
  }
  const listed = [...additives.values()].sort(
    (x, y) =>
      Number(y.additive.flagged) - Number(x.additive.flagged) ||
      y.products.length - x.products.length ||
      x.additive.name.localeCompare(y.additive.name),
  );
  return {
    count: products.length,
    grades,
    ungraded,
    ultraProcessed,
    noNova,
    high: [...high.entries()]
      .map(([nutrient, count]) => ({ nutrient, name: NUTRIENT_NAMES[nutrient], count }))
      .sort((x, y) => y.count - x.count),
    additives: listed,
    flaggedAdditives: listed.filter((a) => a.additive.flagged).length,
  };
}
