import Link from "next/link";
import { ViewTransition } from "react";

import { GradeChip } from "@/components/label/primitives";
import type { CategoryUse, ProductSummary } from "@/lib/api";
import { formatCount } from "@/lib/format";

/** A bar per category, in ink, as long as its count against the first (DESIGN.md, "Additive guide"). */
export function CategoryBars({ categories }: { categories: CategoryUse[] }) {
  const most = Math.max(1, ...categories.map((c) => c.products));
  return (
    <ol className="pt-3">
      {categories.map((category) => (
        <li
          key={category.category_id}
          className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)_auto] items-center gap-3 py-1 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)_auto]"
        >
          <span className="type-data-label break-words">{category.name}</span>
          <span className="block h-3" aria-hidden="true">
            <span
              data-bar
              className="block h-full bg-ink"
              style={{ width: `${(100 * category.products) / most}%` }}
            />
          </span>
          <span className="type-data-value tabular-nums">{formatCount(category.products)}</span>
        </li>
      ))}
    </ol>
  );
}

/** Products as label rows: name, brand and grade, each linking to its page. */
export function ProductRows({ products }: { products: ProductSummary[] }) {
  return (
    <ol>
      {products.map((product) => (
        <li key={product.code} className="border-b border-rule-light py-3">
          <Link
            href={`/product/${product.code}`}
            className="flex items-center justify-between gap-4 no-underline"
          >
            <span className="min-w-0">
              <ViewTransition name={`name-${product.code}`} share="morph" default="none">
                <span className="type-data-value block break-words">{product.name}</span>
              </ViewTransition>
              <span className="type-small block break-words text-ink-muted">
                {product.brand ?? "Brand not listed"}
              </span>
            </span>
            <span className="shrink-0">
              <GradeChip grade={product.nutriscore_grade} />
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}
