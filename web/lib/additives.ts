/** The additive guide's pure parts: addresses and the list filter. */
import type { AdditiveListItem } from "./api";

/** An additive's guide page: its Open Food Facts id without "en:" (en:e330 → /additives/e330). */
export function additiveHref(additiveId: string): string {
  const slug = additiveId.startsWith("en:") ? additiveId.slice(3) : additiveId;
  return `/additives/${encodeURIComponent(slug)}`;
}

/** Lower case, with spaces, hyphens and dots dropped, so "E 330", "e-330" and "E330" agree. */
function squash(text: string): string {
  return text.toLowerCase().replace(/[\s.\-]/g, "");
}

/**
 * What additives do, as the guide's filter offers it: Open Food Facts' function (in US
 * spelling, comma-separated in the data), most useful to a shopper first.
 */
export const FUNCTIONS = [
  { key: "color", label: "Colours" },
  { key: "preservative", label: "Preservatives" },
  { key: "sweetener", label: "Sweeteners" },
  { key: "emulsifier", label: "Emulsifiers" },
  { key: "thickener", label: "Thickeners" },
  { key: "stabilizer", label: "Stabilisers" },
  { key: "antioxidant", label: "Antioxidants" },
  { key: "humectant", label: "Humectants" },
] as const;
export type FunctionKey = (typeof FUNCTIONS)[number]["key"];

/** How many the guide shows before "Show all", when nothing narrows it. */
export const TOP = 50;

export function hasFunction(item: AdditiveListItem, key: FunctionKey): boolean {
  return (item.function ?? "")
    .split(",")
    .some((f) => f.trim().toLowerCase() === key);
}

/** Additives whose name or E number contains the query, keeping the list's order. */
export function filterAdditives(
  items: AdditiveListItem[],
  query: string,
  flaggedOnly = false,
  fn: FunctionKey | null = null,
): AdditiveListItem[] {
  const q = squash(query.trim());
  return items.filter(
    (item) =>
      (!flaggedOnly || item.flagged) &&
      (!fn || hasFunction(item, fn)) &&
      (!q || squash(item.name).includes(q) || squash(item.e_number ?? "").includes(q)),
  );
}
