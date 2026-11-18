import Link from "next/link";

import { CompareTable } from "@/components/compare/compare-table";
import { Rule } from "@/components/label/primitives";
import { AdditiveList } from "@/components/product/additive-list";
import { IngredientList } from "@/components/product/ingredient-list";
import { NutritionPanel } from "@/components/product/nutrition-panel";
import { SwapList } from "@/components/product/swap-list";
import { addProductUrl } from "@/lib/barcode";
import { LABEL, SCAN } from "@/lib/copy";
import { labelAsProduct, type LabelResponse } from "@/lib/label";

/** A label read from photos, laid out like a product page (DESIGN.md, "Read a label"). */
export function LabelResult({ result }: { result: LabelResponse }) {
  const { label, match } = result;
  if (!result.is_food_label || !label) {
    return <p className="type-body pt-8">{LABEL.notALabel}</p>;
  }
  const meta = [label.brand, label.category_name].filter(Boolean).join(", ");
  return (
    <article
      aria-label="What the label says"
      className="grid grid-cols-1 gap-y-8 pt-12 lg:grid-cols-[minmax(0,1fr)_24rem] lg:grid-rows-[auto_1fr] lg:gap-x-16 lg:gap-y-12"
    >
      <header className="min-w-0 lg:col-start-1 lg:row-start-1">
        <h2 className="type-display break-words">{label.name ?? "This product"}</h2>
        <p className="type-body pt-3 text-ink-muted">{meta || "Brand not read"}</p>
        <p className="type-small pt-1 text-ink-muted">{LABEL.readByAi}</p>
      </header>

      <aside className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
        <div className="lg:sticky lg:top-8">
          <NutritionPanel nutrition={label.nutrition} />
          {label.conversion_note && (
            <p className="type-small pt-3 text-ink-muted">{label.conversion_note}</p>
          )}
        </div>
      </aside>

      <div className="min-w-0 lg:col-start-1 lg:row-start-2">
        <section aria-labelledby="label-additives">
          <h3 id="label-additives" className="type-heading pb-2">
            Additives ({label.additives.length})
          </h3>
          <Rule weight="thin" />
          {label.additives.length > 0 ? (
            <AdditiveList additives={label.additives} />
          ) : (
            <p className="type-body pt-3">No additives were read from the label.</p>
          )}
          {label.unmatched_additives.length > 0 && (
            <p className="type-small pt-3 text-ink-muted">
              {LABEL.unmatchedAdditives(label.unmatched_additives)}
            </p>
          )}
        </section>

        <section aria-labelledby="label-ingredients" className="pt-12">
          <h3 id="label-ingredients" className="type-heading pb-2">
            Ingredients ({label.ingredients.length})
          </h3>
          <Rule weight="thin" />
          {label.ingredients.length > 0 ? (
            <IngredientList ingredients={label.ingredients} />
          ) : (
            <p className="type-body pt-3">No ingredient list was read.</p>
          )}
        </section>

        <section aria-labelledby="label-match" className="pt-12">
          <h3 id="label-match" className="type-heading pb-2">
            {match ? LABEL.looksLike : LABEL.noMatch}
          </h3>
          <Rule weight="thin" />
          {match ? (
            <>
              <p className="type-body pt-3">
                <Link href={`/product/${match.product.code}`} className="type-data-value">
                  {match.product.name}
                </Link>
                {match.product.brand ? `, ${match.product.brand}` : ""}
                {match.how === "barcode" ? " (by its barcode)" : " (by its name and brand)"}
              </p>
              <div className="pt-6">
                <CompareTable a={labelAsProduct(label)} b={match.product} />
              </div>
            </>
          ) : label.barcode ? (
            <p className="type-body pt-3">
              {LABEL.barcodeMissing(label.barcode)}{" "}
              <a href={addProductUrl(label.barcode)}>{SCAN.addIt}</a>.
            </p>
          ) : (
            <p className="type-body pt-3">
              No product in the US data matched its name and brand.
            </p>
          )}
        </section>

        {result.suggestions.length > 0 && (
          <section aria-labelledby="label-suggestions" className="pt-12">
            <h3 id="label-suggestions" className="type-heading pb-2">
              {result.suggestions_kind === "swaps"
                ? LABEL.swapsHeading
                : LABEL.categoryHeading(label.category_name)}
            </h3>
            <Rule weight="thin" />
            <SwapList
              swaps={result.suggestions}
              from={result.suggestions_kind === "swaps" ? match?.product.code : undefined}
            />
            {result.suggestions_kind === "category" && (
              <p className="type-small pt-3 text-ink-muted">{LABEL.categoryNote}</p>
            )}
          </section>
        )}
      </div>
    </article>
  );
}
