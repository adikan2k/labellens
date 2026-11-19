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

/** Additives whose name or E number contains the query, keeping the list's order. */
export function filterAdditives(
  items: AdditiveListItem[],
  query: string,
  flaggedOnly = false,
): AdditiveListItem[] {
  const q = squash(query.trim());
  return items.filter(
    (item) =>
      (!flaggedOnly || item.flagged) &&
      (!q || squash(item.name).includes(q) || squash(item.e_number ?? "").includes(q)),
  );
}
