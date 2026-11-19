/**
 * High in, low in: fat, saturates, sugars and salt against the UK's front-of-pack criteria,
 * the only published per-100 g standard (the US has none).
 *
 * Source: UK Department of Health and Social Care, "Guide to creating a front of pack (FoP)
 * nutrition label for pre-packed products sold through retail outlets" (2016); the same
 * tables are Annex D of the Scottish Government's "Supporting Healthy Choices" (tables 1a and
 * 1b), checked 2026-11-18. Low is at or under the first figure; high is over the second.
 * The per-portion criteria (portions over 100 g, or 150 ml for drinks) are not applied: the
 * site works per 100 g, and serving sizes are often missing.
 */
import type { Nutrition } from "./api";

export const THRESHOLD_SOURCE = {
  name: "the UK front-of-pack criteria",
  url: "https://www.gov.scot/publications/supporting-healthy-choices-framework-voluntary-action/pages/13/",
} as const;

export type FlaggedNutrient = "fat_100g" | "saturated_fat_100g" | "sugars_100g" | "salt_100g";
export type Level = "low" | "medium" | "high";

type Band = { low: number; high: number };

export const THRESHOLDS: Record<"food" | "drink", Record<FlaggedNutrient, Band>> = {
  food: {
    fat_100g: { low: 3.0, high: 17.5 },
    saturated_fat_100g: { low: 1.5, high: 5.0 },
    sugars_100g: { low: 5.0, high: 22.5 },
    salt_100g: { low: 0.3, high: 1.5 },
  },
  drink: {
    fat_100g: { low: 1.5, high: 8.75 },
    saturated_fat_100g: { low: 0.75, high: 2.5 },
    sugars_100g: { low: 2.5, high: 11.25 },
    salt_100g: { low: 0.3, high: 0.75 },
  },
};

export const NUTRIENT_NAMES: Record<FlaggedNutrient, string> = {
  fat_100g: "fat",
  saturated_fat_100g: "saturates",
  sugars_100g: "sugars",
  salt_100g: "salt",
};

/** Categories judged as drinks, per 100 ml. Cream sits in "milk" and is judged as a drink too. */
export const DRINK_CATEGORIES = new Set(["sodas", "juices", "water-coffee-tea", "milk"]);

export function isDrink(categoryId: string | null | undefined): boolean {
  return !!categoryId && DRINK_CATEGORIES.has(categoryId);
}

/** Low at or under the low figure, high over the high one; null when the value is unknown. */
export function level(value: number | null, band: Band): Level | null {
  if (value === null || Number.isNaN(value)) return null;
  if (value <= band.low) return "low";
  if (value > band.high) return "high";
  return "medium";
}

export type Flag = { nutrient: FlaggedNutrient; name: string; level: "low" | "high" };

/** The high and low flags for a product, high first, each in label order. */
export function nutrientFlags(nutrition: Nutrition, categoryId: string | null | undefined): Flag[] {
  const table = THRESHOLDS[isDrink(categoryId) ? "drink" : "food"];
  const order: FlaggedNutrient[] = ["fat_100g", "saturated_fat_100g", "sugars_100g", "salt_100g"];
  const flags = order.flatMap((nutrient) => {
    const l = level(nutrition[nutrient], table[nutrient]);
    return l === "low" || l === "high" ? [{ nutrient, name: NUTRIENT_NAMES[nutrient], level: l }] : [];
  });
  return [...flags.filter((f) => f.level === "high"), ...flags.filter((f) => f.level === "low")];
}

/** The level of one nutrient, for the comparison table; null for medium or unknown. */
export function flagFor(
  nutrient: string,
  value: number | null,
  categoryId: string | null | undefined,
): "low" | "high" | null {
  if (!(nutrient in NUTRIENT_NAMES)) return null;
  const table = THRESHOLDS[isDrink(categoryId) ? "drink" : "food"];
  const l = level(value, table[nutrient as FlaggedNutrient]);
  return l === "medium" ? null : l;
}
