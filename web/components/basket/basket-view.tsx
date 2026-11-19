"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { CHIP_CLASSES, GradeChip, Rule } from "@/components/label/primitives";
import { getProduct, getSwaps, type NutriscoreGrade, type Product, type Swap } from "@/lib/api";
import {
  removeFromBasket,
  replaceInBasket,
  shareHref,
  summarise,
  writeBasket,
  type BasketSummary,
} from "@/lib/basket";
import { BASKET } from "@/lib/copy";
import { useBasket } from "@/lib/use-basket";
import { nutrientFlags } from "@/lib/thresholds";

type Loaded = Record<string, Product | "missing" | undefined>;

/** Products for the barcodes, fetched once each; "missing" for barcodes no longer in the data. */
function useProducts(codes: string[]): Loaded {
  const [loaded, setLoaded] = useState<Loaded>({});
  useEffect(() => {
    let live = true;
    for (const code of codes) {
      if (loaded[code] !== undefined) continue;
      getProduct(code)
        .then((body) => live && setLoaded((m) => ({ ...m, [code]: body.product })))
        .catch(() => live && setLoaded((m) => ({ ...m, [code]: "missing" })));
    }
    return () => {
      live = false;
    };
    // Each barcode is fetched once; `loaded` only grows.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.join(",")]);
  return loaded;
}

/** The top swap for each product that has one (the product page's rule). */
function useSwaps(products: Product[]): Record<string, Swap | null> {
  const [swaps, setSwaps] = useState<Record<string, Swap | null>>({});
  const key = products.map((p) => p.code).join(",");
  useEffect(() => {
    let live = true;
    for (const product of products) {
      if (product.code in swaps || product.nutriscore_grade === "a") continue;
      getSwaps(product.code, 1)
        .then((body) => live && setSwaps((m) => ({ ...m, [product.code]: body.swaps[0] ?? null })))
        .catch(() => live && setSwaps((m) => ({ ...m, [product.code]: null })));
    }
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return swaps;
}

/** My basket, or a shared one (read-only until saved). DESIGN.md, "My basket". */
export function BasketView({ shared }: { shared: string[] | null }) {
  const router = useRouter();
  const mine = useBasket();
  const codes = shared ?? mine;
  const loaded = useProducts(codes);
  const products = useMemo(
    () => codes.flatMap((c) => (loaded[c] && loaded[c] !== "missing" ? [loaded[c] as Product] : [])),
    [codes, loaded],
  );
  const swaps = useSwaps(shared ? [] : products);
  const summary = summarise(products);
  const pending = codes.some((c) => loaded[c] === undefined);

  if (codes.length === 0) {
    return (
      <section aria-labelledby="basket-empty" className="max-w-measure pt-6">
        <h2 id="basket-empty" className="type-heading">
          {BASKET.emptyTitle}
        </h2>
        <p className="type-body pt-2">{BASKET.emptyBody}</p>
        <p className="type-data-value flex flex-wrap gap-x-6 gap-y-2 pt-4">
          <Link href="/">Search</Link>
          <Link href="/label">Read a label</Link>
        </p>
      </section>
    );
  }

  return (
    <div className="max-w-measure">
      {shared && (
        <div className="panel mt-6 p-4">
          <h2 className="type-heading">{BASKET.sharedTitle}</h2>
          <p className="type-body pt-2">{BASKET.sharedNote}</p>
          <button
            type="button"
            className="type-data-value mt-3 cursor-pointer rounded-control bg-ink px-4 py-2 text-paper"
            onClick={() => {
              writeBasket(shared);
              router.push("/basket");
            }}
          >
            {BASKET.save}
          </button>
        </div>
      )}

      <Summary summary={summary} />
      {pending && <p className="type-small pt-3 text-ink-muted">{BASKET.loading}</p>}

      <ol aria-label="Products in the basket" className="pt-8">
        {codes.map((code) => {
          const item = loaded[code];
          if (item === undefined) return null;
          if (item === "missing") {
            return (
              <li key={code} className="flex justify-between gap-4 border-b border-rule-light py-3">
                <span className="type-body text-ink-muted">{BASKET.missing(code)}</span>
                {!shared && <RemoveButton code={code} name={code} />}
              </li>
            );
          }
          return (
            <Item key={code} product={item} swap={swaps[code] ?? null} readOnly={!!shared} />
          );
        })}
      </ol>

      <Additives summary={summary} />

      {!shared && <Share codes={codes} />}
    </div>
  );
}

function RemoveButton({ code, name }: { code: string; name: string }) {
  return (
    <button
      type="button"
      className="type-small shrink-0 cursor-pointer underline underline-offset-2"
      aria-label={`${BASKET.remove} ${name}`}
      onClick={() => removeFromBasket(code)}
    >
      {BASKET.remove}
    </button>
  );
}

function Item({ product, swap, readOnly }: { product: Product; swap: Swap | null; readOnly: boolean }) {
  const high = nutrientFlags(product.nutrition, product.category_main).filter((f) => f.level === "high");
  return (
    <li className="border-b border-rule-light py-4">
      <div className="flex items-start justify-between gap-4">
        <span className="min-w-0">
          <Link href={`/product/${product.code}`} className="type-data-value block break-words">
            {product.name}
          </Link>
          <span className="type-small block text-ink-muted">
            {[product.brand, product.nova_group === 4 ? "ultra-processed" : null]
              .filter(Boolean)
              .join(" · ") || "Brand not listed"}
          </span>
          {high.length > 0 && (
            <span className="type-small block pt-1">{high.map((f) => `High in ${f.name}`).join(" · ")}</span>
          )}
        </span>
        <span className="flex shrink-0 flex-col items-end gap-2">
          <GradeChip grade={product.nutriscore_grade} />
          {!readOnly && <RemoveButton code={product.code} name={product.name ?? product.code} />}
        </span>
      </div>
      {!readOnly && swap && (
        <p className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pt-3">
          <span className="type-small min-w-0">
            {BASKET.swapLine(swap.product.name ?? "a product", swap.reason)}
          </span>
          <button
            type="button"
            className="type-data-value shrink-0 cursor-pointer rounded-control border-2 border-ink px-3 py-1"
            aria-label={`${BASKET.swap} ${product.name} for ${swap.product.name}`}
            onClick={() => replaceInBasket(product.code, swap.product.code)}
          >
            {BASKET.swap}
          </button>
        </p>
      )}
    </li>
  );
}

const GRADES: NutriscoreGrade[] = ["a", "b", "c", "d", "e"];

export function Summary({ summary }: { summary: BasketSummary }) {
  const graded = GRADES.reduce((n, g) => n + summary.grades[g], 0);
  const facts = [
    `${summary.count} product${summary.count === 1 ? "" : "s"}`,
    `${summary.ultraProcessed} ultra-processed`,
    `${summary.flaggedAdditives} flagged additive${summary.flaggedAdditives === 1 ? "" : "s"}`,
  ];
  return (
    <section aria-label="The basket together" className="pt-6">
      <p className="type-data-value">{facts.join(" · ")}</p>
      {graded > 0 && (
        <ol aria-label={BASKET.gradeBarLabel} className="flex h-12 pt-3">
          {GRADES.filter((g) => summary.grades[g] > 0).map((g) => (
            <li
              key={g}
              data-grade={g}
              style={{ flexGrow: summary.grades[g], flexBasis: 0 }}
              className={`type-data-value flex min-w-8 items-center justify-center ${CHIP_CLASSES[g]}`}
            >
              <span aria-hidden="true">{g.toUpperCase()}</span>
              <span className="sr-only">
                Nutri-Score {g.toUpperCase()}: {summary.grades[g]}
              </span>
            </li>
          ))}
        </ol>
      )}
      {summary.ungraded > 0 && (
        <p className="type-small pt-2 text-ink-muted">
          {summary.ungraded} with no Nutri-Score.
        </p>
      )}
      {summary.high.length > 0 && (
        <p className="type-body pt-3">
          {summary.high.map((h) => `High in ${h.name}: ${h.count}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

function Additives({ summary }: { summary: BasketSummary }) {
  return (
    <section aria-labelledby="basket-additives" className="pt-12">
      <h2 id="basket-additives" className="type-heading pb-2">
        {BASKET.additivesTitle}
      </h2>
      <Rule weight="thin" />
      {summary.additives.length === 0 ? (
        <p className="type-body pt-3">{BASKET.noAdditives}</p>
      ) : (
        <ul>
          {summary.additives.map(({ additive, products }) => (
            <li key={additive.additive_id} className="border-b border-rule-light py-2">
              <span className="type-data-label">
                {additive.e_number && <span className="type-data-value pr-2">{additive.e_number}</span>}
                {additive.name}
              </span>
              <span className="type-small block text-ink-muted">
                In {products.length} product{products.length === 1 ? "" : "s"}
                {additive.flagged ? " · Flagged by Open Food Facts" : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Share({ codes }: { codes: string[] }) {
  const [copied, setCopied] = useState(false);
  const href = shareHref(codes);
  return (
    <p className="type-small flex flex-wrap items-baseline gap-x-4 gap-y-1 pt-8">
      <Link href={href}>{BASKET.share}</Link>
      <button
        type="button"
        className="cursor-pointer underline underline-offset-2"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(new URL(href, window.location.href).toString());
            setCopied(true);
          } catch {
            setCopied(false);
          }
        }}
      >
        Copy link
      </button>
      <span role="status">{copied ? BASKET.copied : ""}</span>
    </p>
  );
}
