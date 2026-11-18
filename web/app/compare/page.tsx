import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { CompareTable } from "@/components/compare/compare-table";
import { PickProduct } from "@/components/compare/pick-product";
import { GradeChip, Rule } from "@/components/label/primitives";
import type { Product } from "@/lib/api";
import { cachedProduct } from "@/lib/cached";
import { parseCodes } from "@/lib/compare";
import { COMPARE_INTRO, WAKING_UP } from "@/lib/copy";
import { COMPARE_TITLE, compareTitle } from "@/lib/metadata";

type Loaded =
  | { kind: "products"; products: Product[] }
  | { kind: "missing"; products: Product[]; missing: string[] }
  | { kind: "unavailable" };

/** Both products at once, through the same cached read as the product page. */
async function load(codes: string[]): Promise<Loaded> {
  const results = await Promise.allSettled(codes.map((code) => cachedProduct(code)));
  if (results.some((r) => r.status === "rejected")) return { kind: "unavailable" };
  const values = results.map((r) => (r.status === "fulfilled" ? r.value : null));
  const products = values.flatMap((v) => (v ? [v.product] : []));
  const missing = codes.filter((_, i) => values[i] === null);
  return missing.length > 0 ? { kind: "missing", products, missing } : { kind: "products", products };
}

export async function generateMetadata({ searchParams }: PageProps<"/compare">): Promise<Metadata> {
  const codes = parseCodes((await searchParams).codes);
  if (codes.length === 0) return { title: COMPARE_TITLE };
  const loaded = await load(codes).catch(() => ({ kind: "unavailable" }) as const);
  return { title: loaded.kind === "unavailable" ? COMPARE_TITLE : compareTitle(loaded.products) };
}

/** Not async: search params are read inside the Suspense boundary, so the shell prerenders. */
export default function ComparePage({ searchParams }: PageProps<"/compare">) {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <h1 className="type-title pb-2">Compare</h1>
      <p className="type-body max-w-measure pb-8 text-ink-muted">{COMPARE_INTRO}</p>
      <Suspense fallback={<p className="type-body min-h-dvh text-ink-muted">Reading the labels…</p>}>
        {searchParams.then(({ codes }) => (
          <CompareView codes={parseCodes(codes)} />
        ))}
      </Suspense>
    </div>
  );
}

async function CompareView({ codes }: { codes: string[] }) {
  if (codes.length === 0) {
    return (
      <div className="max-w-measure">
        <PickProduct chosen={[]} label="First product" />
      </div>
    );
  }
  const loaded = await load(codes);
  if (loaded.kind === "unavailable") {
    return (
      <p className="type-body max-w-measure">
        {WAKING_UP} <Link href={`/compare?codes=${codes.join(",")}`}>Try again</Link>.
      </p>
    );
  }
  const { products } = loaded;
  return (
    <>
      {loaded.kind === "missing" && (
        <p role="status" className="type-body max-w-measure pb-6">
          {loaded.missing.length === 1
            ? `No product with barcode ${loaded.missing[0]} in this snapshot.`
            : `No products with barcodes ${loaded.missing.join(" or ")} in this snapshot.`}
        </p>
      )}
      {products.length === 2 ? (
        <CompareTable a={products[0]} b={products[1]} />
      ) : products.length === 1 ? (
        <OneChosen product={products[0]} />
      ) : (
        <div className="max-w-measure">
          <PickProduct chosen={[]} label="First product" />
        </div>
      )}
    </>
  );
}

/** One product picked: it stands on the left, and the search picks the other. */
function OneChosen({ product }: { product: Product }) {
  return (
    <div className="grid grid-cols-1 gap-8 md:grid-cols-2 md:gap-12">
      <section aria-label="First product" className="panel px-4 pt-3 pb-4">
        <Rule weight="heavy" />
        <p className="pt-3">
          <Link href={`/product/${product.code}`} className="type-data-value break-words">
            {product.name}
          </Link>
        </p>
        <p className="type-small break-words text-ink-muted">{product.brand ?? "Brand not listed"}</p>
        <p className="pt-3">
          <GradeChip grade={product.nutriscore_grade} />
        </p>
      </section>
      <PickProduct chosen={[product.code]} label="Compare with" />
    </div>
  );
}
