/**
 * Dashboard headings, computed from the numbers (DESIGN.md: each chart's heading states its
 * finding). Pure functions, so every sentence is tested against the data it summarises.
 */
import type { CountByKey, StatsOverview } from "./api";
import { formatCount } from "./format";

const pct = (part: number, whole: number) => (whole ? Math.round((100 * part) / whole) : 0);

export function nutriscoreFinding(rows: CountByKey[]): string {
  const graded = rows.filter((r) => r.key);
  const total = graded.reduce((s, r) => s + r.count, 0);
  if (!total) return "No products have a Nutri-Score yet";
  const worse = graded.filter((r) => ["c", "d", "e"].includes(r.key ?? "")).reduce((s, r) => s + r.count, 0);
  return `${pct(worse, total)}% of graded US products score C or worse`;
}

export function novaFinding(rows: CountByKey[]): string {
  const known = rows.filter((r) => r.key);
  const total = known.reduce((s, r) => s + r.count, 0);
  if (!total) return "No products have a NOVA group yet";
  const ultra = known.find((r) => r.key === "4")?.count ?? 0;
  return `${pct(ultra, total)}% of products with a NOVA group are ultra-processed`;
}

export function largestFinding(rows: CountByKey[], noun: string): string {
  const top = [...rows].sort((a, b) => b.count - a.count)[0];
  if (!top || !top.count) return `No ${noun} data yet`;
  return `${top.label} is the largest ${noun}, with ${formatCount(top.count)} products`;
}

/** Where categories came from, for the note under the category chart. */
export function categorySourceNote(rows: CountByKey[]): string {
  const total = rows.reduce((s, r) => s + r.count, 0);
  const count = (key: string | null) => rows.find((r) => r.key === key)?.count ?? 0;
  const parts = [
    `${pct(count("off_tags"), total)}% of products are placed by their Open Food Facts category tags`,
  ];
  if (count("model")) {
    parts.push(`${pct(count("model"), total)}% by AI from the name and ingredients, where the tags give none`);
  }
  return `${parts.join("; ")}. “Other or unclear” is left out.`;
}

export function additiveFinding(rows: CountByKey[]): string {
  const top = [...rows].sort((a, b) => b.count - a.count)[0];
  if (!top) return "No additive data yet";
  return `${top.label} is in more products than any other additive: ${formatCount(top.count)}`;
}

export type CategoryShare = { name: string; share: number; graded: number };

export function poorGradeShares(stats: StatsOverview): CategoryShare[] {
  return stats.nutriscore_by_category
    .map((c) => ({
      name: c.name,
      graded: c.graded_count,
      share: c.graded_count ? (c.grades.d + c.grades.e) / c.graded_count : 0,
    }))
    .sort((a, b) => b.share - a.share);
}

export function poorGradeFinding(stats: StatsOverview): string {
  const top = poorGradeShares(stats)[0];
  if (!top) return "Not enough graded products per category yet";
  return `${top.name}: ${Math.round(top.share * 100)}% score D or E, the most of any category`;
}

export function sugarFinding(stats: StatsOverview): string {
  const top = [...stats.median_sugars_by_category].sort((a, b) => b.median - a.median)[0];
  if (!top) return "Not enough sugar values per category yet";
  return `${top.name} have the most sugar: a median of ${top.median} g per 100 g`;
}
