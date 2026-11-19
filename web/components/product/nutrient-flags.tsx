import type { Nutrition } from "@/lib/api";
import { isDrink, nutrientFlags, THRESHOLD_SOURCE } from "@/lib/thresholds";

/**
 * High in, low in (DESIGN.md, Product page): words under the Nutrition Facts panel, by the UK
 * front-of-pack criteria. Words only; colour belongs to Nutri-Score. Nothing when nothing is
 * high or low.
 */
export function NutrientFlags({
  nutrition,
  categoryId,
}: {
  nutrition: Nutrition;
  categoryId: string | null | undefined;
}) {
  const flags = nutrientFlags(nutrition, categoryId);
  if (flags.length === 0) return null;
  const high = flags.filter((f) => f.level === "high");
  const low = flags.filter((f) => f.level === "low");
  const per = isDrink(categoryId) ? "per 100 ml, as a drink" : "per 100 g";
  return (
    <section aria-label="High in, low in" className="pt-4">
      <ul>
        {high.map((f) => (
          <li key={f.nutrient} className="type-data-value">
            High in {f.name}
          </li>
        ))}
      </ul>
      {low.length > 0 && (
        <p className="type-data-label pt-1">{low.map((f) => `Low in ${f.name}`).join(" · ")}</p>
      )}
      <p className="type-small pt-2 text-ink-muted">
        By <a href={THRESHOLD_SOURCE.url}>{THRESHOLD_SOURCE.name}</a>, {per}.
      </p>
    </section>
  );
}
