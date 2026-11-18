/** The Nutrition Facts rows, shared by the product page's panel and the comparison. */
import type { Nutrition } from "./api";

export type NutritionKey = keyof Nutrition;
export type NutritionRow = { key: NutritionKey; label: string; noun: string; indent?: boolean };

// US label order, grouped: rule-medium between groups, rule-thin between rows (DESIGN.md).
export const GROUPS: NutritionRow[][] = [
  [{ key: "energy_kcal_100g", label: "Energy", noun: "energy" }],
  [
    { key: "fat_100g", label: "Fat", noun: "fat" },
    { key: "saturated_fat_100g", label: "Saturated fat", noun: "saturated fat", indent: true },
  ],
  [{ key: "salt_100g", label: "Salt", noun: "salt" }],
  [
    { key: "fiber_100g", label: "Fiber", noun: "fiber" },
    { key: "sugars_100g", label: "Sugars", noun: "sugar" },
  ],
  [{ key: "proteins_100g", label: "Protein", noun: "protein" }],
];
