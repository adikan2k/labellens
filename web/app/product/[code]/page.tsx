import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense, ViewTransition } from "react";

import { Rule } from "@/components/label/primitives";
import { AdditiveList } from "@/components/product/additive-list";
import { IngredientList } from "@/components/product/ingredient-list";
import { SwapList } from "@/components/product/swap-list";
import { AddToBasket } from "@/components/basket/add-to-basket";
import { NutrientFlags } from "@/components/product/nutrient-flags";
import { NutritionPanel } from "@/components/product/nutrition-panel";
import { SettleChip } from "@/components/product/settle-chip";
import { YourRules } from "@/components/preferences/your-rules";
import type { Product, Swap } from "@/lib/api";
import { cachedProduct, cachedSwaps } from "@/lib/cached";
import { compareHref } from "@/lib/compare";
import {
  AI_CATEGORY_NOTE,
  COMPARE_WITH,
  noSwapsReason,
  SWAP_RULE,
  SWAPS_UNAVAILABLE,
  WAKING_UP,
} from "@/lib/copy";
import { NOVA_LABELS } from "@/lib/format";
import {
  PRODUCT_NOT_FOUND_TITLE,
  PRODUCT_UNAVAILABLE_TITLE,
  productDescription,
  productTitle,
  social,
} from "@/lib/metadata";

/** "Lucky Charms (Lucky Charms) · LabelLens". Shares the cached product read with the page. */
export async function generateMetadata({
  params,
}: PageProps<"/product/[code]">): Promise<Metadata> {
  const { code } = await params;
  try {
    const result = await cachedProduct(code);
    if (!result) return { title: PRODUCT_NOT_FOUND_TITLE };
    const title = productTitle(result.product);
    const description = productDescription(result.product);
    return { title, description, ...social(title, description) };
  } catch {
    return { title: PRODUCT_UNAVAILABLE_TITLE };
  }
}

/** Not async: params are awaited inside the Suspense boundary, so the shell prerenders. */
export default function ProductPage({ params }: PageProps<"/product/[code]">) {
  return (
    <Suspense fallback={<ProductSkeleton />}>
      {params.then(({ code }) => (
        <ProductView code={code} />
      ))}
    </Suspense>
  );
}

async function ProductView({ code }: { code: string }) {
  // Product and swaps together, so the page renders once and nothing shifts. A swap failure
  // leaves the label standing with a note; a product failure means unavailable.
  const [productResult, swapsResult] = await Promise.allSettled([
    cachedProduct(code),
    cachedSwaps(code),
  ]);
  if (productResult.status === "rejected") {
    // Errors from a cached function arrive without their class; any of them means unavailable.
    return <Unavailable code={code} />;
  }
  if (!productResult.value) notFound();
  const swaps = swapsResult.status === "fulfilled" ? swapsResult.value.swaps : null;
  return <ProductLayout product={productResult.value.product} swaps={swaps} />;
}

function ProductLayout({ product, swaps }: { product: Product; swaps: Swap[] | null }) {
  const meta = [product.brand, product.category_name].filter(Boolean).join(", ");
  return (
    // One panel, placed by the grid: after the name on phones, a sticky right column on desktop.
    <article className="mx-auto grid w-full max-w-page grid-cols-1 gap-y-8 px-4 pt-8 pb-16 lg:grid-cols-[minmax(0,1fr)_24rem] lg:grid-rows-[auto_1fr] lg:gap-x-16 lg:gap-y-12">
      <header className="min-w-0 lg:col-start-1 lg:row-start-1">
        <ViewTransition name={`name-${product.code}`} share="morph" default="none">
          <h1 className="type-display break-words">{product.name}</h1>
        </ViewTransition>
        <p className="type-body pt-3 text-ink-muted">{meta || "Brand not listed"}</p>
        {product.category_source === "model" && (
          <p className="type-small pt-1 text-ink-muted">{AI_CATEGORY_NOTE}</p>
        )}

        <dl className="pt-8">
          <div className="flex items-center gap-4 pb-3">
            <dt className="type-data-label">Nutri-Score</dt>
            <dd>
              <SettleChip code={product.code} grade={product.nutriscore_grade} />
            </dd>
          </div>
          <div className="flex items-baseline gap-4">
            <dt className="type-data-label">Processing</dt>
            <dd className="type-data-value">
              {product.nova_group
                ? `NOVA ${product.nova_group}: ${NOVA_LABELS[product.nova_group]}`
                : "Open Food Facts has no NOVA group for this product."}
            </dd>
          </div>
        </dl>
      </header>

      <aside className="lg:col-start-2 lg:row-span-2 lg:row-start-1">
        <div className="lg:sticky lg:top-8">
          <NutritionPanel nutrition={product.nutrition} />
          <NutrientFlags nutrition={product.nutrition} categoryId={product.category_main} />
          <YourRules subject={product} />
        </div>
      </aside>

      <div className="min-w-0 lg:col-start-1 lg:row-start-2">
        <section aria-labelledby="additives">
          <h2 id="additives" className="type-heading pb-2">
            Additives ({product.additives.length})
          </h2>
          <Rule weight="thin" />
          {product.additives.length > 0 ? (
            <AdditiveList additives={product.additives} />
          ) : (
            <p className="type-body pt-3">Open Food Facts lists no additives for this product.</p>
          )}
        </section>

        <section aria-labelledby="swaps" className="pt-12">
          <h2 id="swaps" className="type-heading pb-2">
            Better swaps
          </h2>
          <Rule weight="thin" />
          {swaps === null ? (
            <p className="type-body pt-3">{SWAPS_UNAVAILABLE}</p>
          ) : swaps.length > 0 ? (
            <>
              <SwapList swaps={swaps} from={product.code} />
              <p className="type-small pt-3 text-ink-muted">{SWAP_RULE}</p>
            </>
          ) : (
            <p className="type-body pt-3">{noSwapsReason(product)}</p>
          )}
        </section>

        <section aria-labelledby="ingredients" className="pt-12">
          <h2 id="ingredients" className="type-heading pb-2">
            Ingredients ({product.ingredients.length})
          </h2>
          <Rule weight="thin" />
          {product.ingredients.length > 0 ? (
            <IngredientList ingredients={product.ingredients} />
          ) : (
            <p className="type-body pt-3">Open Food Facts has no ingredient list for this product.</p>
          )}
          <p className="type-small pt-3 text-ink-muted">
            In label order. Only ingredients Open Food Facts recognises are listed; the most
            common open to say what they are.
          </p>
        </section>

        <p className="flex flex-wrap gap-x-6 gap-y-2 pt-12">
          <a href={product.off_url} className="type-data-value">
            Open in Open Food Facts
          </a>
          <AddToBasket code={product.code} />
          <Link href={compareHref([product.code])} className="type-data-value">
            {COMPARE_WITH}
          </Link>
          {product.in_graph && (
            <Link href={`/graph?code=${product.code}`} className="type-data-value">
              Explore in the graph
            </Link>
          )}
        </p>
      </div>
    </article>
  );
}

/** A screen tall, so the footer starts below the fold and does not jump when the label streams in. */
function ProductSkeleton() {
  return (
    <div aria-busy="true" className="mx-auto min-h-dvh w-full max-w-page px-4 pt-8 pb-16">
      <p className="type-body text-ink-muted">Reading the label…</p>
    </div>
  );
}

function Unavailable({ code }: { code: string }) {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
      <h1 className="type-page pb-6">This label is not ready</h1>
      <p className="type-body">{WAKING_UP}</p>
      <p className="type-body pt-4">
        <Link href={`/product/${code}`}>Try again</Link> or <Link href="/">search again</Link>.
      </p>
    </div>
  );
}
