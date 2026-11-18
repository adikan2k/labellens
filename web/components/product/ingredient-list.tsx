import type { Ingredient } from "@/lib/api";

import { ExpandableRow, ExplainerText } from "./expandable-row";

/**
 * Ingredients in label order. Those with an explainer (the most common ones) expand like
 * additive rows; the rest are plain rows, since there is nothing more to show.
 */
export function IngredientList({ ingredients }: { ingredients: Ingredient[] }) {
  return (
    <ol className="pt-1">
      {ingredients.map((ingredient) => {
        const label = (
          <span className="type-body flex gap-3">
            <span className="type-data-value w-6 shrink-0 text-right text-ink-muted">
              {ingredient.rank}
            </span>
            <span>{ingredient.name}</span>
          </span>
        );
        return (
          <li key={ingredient.ingredient_id} className="border-b border-rule-light">
            {ingredient.explainer ? (
              <ExpandableRow label={label}>
                {/* Under the name: the same spacer column as the rank. */}
                <div className="flex gap-3">
                  <span aria-hidden="true" className="w-6 shrink-0" />
                  <div>
                    <ExplainerText explainer={ingredient.explainer} />
                  </div>
                </div>
              </ExpandableRow>
            ) : (
              <div className="py-2">{label}</div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
