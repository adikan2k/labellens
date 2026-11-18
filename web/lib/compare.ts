/**
 * Two products side by side: the rows, the differences and the additive groups (DESIGN.md,
 * "Compare"). Facts only: a difference says more or less, never better or worse.
 */
import type { Additive, Nutrition, Product } from "./api";
import { formatEnergy, formatGrams, NOVA_LABELS } from "./format";
import { GROUPS, type NutritionKey } from "./nutrition";

export const MAX_COMPARED = 2;

/** `?codes=A,B` as barcodes: digits only, no repeats, at most two. */
export function parseCodes(raw: string | string[] | undefined): string[] {
  const text = Array.isArray(raw) ? raw.join(",") : (raw ?? "");
  const codes: string[] = [];
  for (const part of text.split(",")) {
    const code = part.trim();
    if (/^\d{1,32}$/.test(code) && !codes.includes(code)) codes.push(code);
    if (codes.length === MAX_COMPARED) break;
  }
  return codes;
}

export function compareHref(codes: string[]): string {
  return `/compare?codes=${codes.join(",")}`;
}

function format(key: NutritionKey, value: number): string {
  return key === "energy_kcal_100g" ? formatEnergy(value) : formatGrams(value);
}

/** The second value against the first: "6 g less", "17 kcal more", "Same", or null if unknown. */
export function difference(key: NutritionKey, a: number | null, b: number | null): string | null {
  if (a === null || b === null) return null;
  // Same as printed is the same: 4.42 g and 4.38 g both read "4.4 g".
  if (format(key, a) === format(key, b)) return "Same";
  const gap = format(key, Math.abs(b - a));
  return `${gap} ${b > a ? "more" : "less"}`;
}

export type CompareRow = {
  key: NutritionKey;
  label: string;
  indent: boolean;
  a: string | null;
  b: string | null;
  difference: string | null;
};

/** Nutrition rows in US label order, grouped as on the product page's panel. */
export function nutritionGroups(a: Nutrition, b: Nutrition): CompareRow[][] {
  return GROUPS.map((group) =>
    group.map((row) => {
      const [va, vb] = [a[row.key], b[row.key]];
      return {
        key: row.key,
        label: row.label,
        indent: row.indent ?? false,
        a: va === null ? null : format(row.key, va),
        b: vb === null ? null : format(row.key, vb),
        difference: difference(row.key, va, vb),
      };
    }),
  );
}

export function processing(product: Pick<Product, "nova_group">): string | null {
  return product.nova_group ? `NOVA ${product.nova_group}` : null;
}

export function novaTitle(product: Pick<Product, "nova_group">): string | undefined {
  return product.nova_group ? NOVA_LABELS[product.nova_group] : undefined;
}

export type AdditiveGroups = { both: Additive[]; onlyA: Additive[]; onlyB: Additive[] };

/** Additives in both, only in the first, only in the second; each list in the first's order. */
export function additiveGroups(a: Additive[], b: Additive[]): AdditiveGroups {
  const inA = new Set(a.map((x) => x.additive_id));
  const inB = new Set(b.map((x) => x.additive_id));
  return {
    both: a.filter((x) => inB.has(x.additive_id)),
    onlyA: a.filter((x) => !inB.has(x.additive_id)),
    onlyB: b.filter((x) => !inA.has(x.additive_id)),
  };
}
