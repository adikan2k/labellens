import Link from "next/link";
import { ViewTransition } from "react";

import { GradeChip } from "@/components/label/primitives";
import type { Swap } from "@/lib/api";
import { compareHref } from "@/lib/compare";

/**
 * Better swaps as label rows: name, brand and grade, then the reason built from the data. Each
 * row also links to a side-by-side comparison with `from`, the product being viewed; it sits
 * beside the row's own link, since links cannot nest.
 */
export function SwapList({ swaps, from }: { swaps: Swap[]; from: string }) {
  return (
    <ol>
      {swaps.map(({ product, reason }) => (
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
              <span className="type-small block pt-1">{reason}</span>
            </span>
            <ViewTransition name={`grade-${product.code}`} share="morph" default="none">
              <span className="shrink-0">
                <GradeChip grade={product.nutriscore_grade} />
              </span>
            </ViewTransition>
          </Link>
          <Link
            href={compareHref([from, product.code])}
            className="type-small inline-block pt-1"
            aria-label={`Compare with ${product.name}`}
          >
            Compare
          </Link>
        </li>
      ))}
    </ol>
  );
}
