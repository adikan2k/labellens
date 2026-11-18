import Link from "next/link";
import { ViewTransition } from "react";

import { GradeChip } from "@/components/label/primitives";
import type { Swap } from "@/lib/api";

/** Better swaps as label rows: name, brand and grade, then the reason built from the data. */
export function SwapList({ swaps }: { swaps: Swap[] }) {
  return (
    <ol>
      {swaps.map(({ product, reason }) => (
        <li key={product.code}>
          <Link
            href={`/product/${product.code}`}
            className="flex items-center justify-between gap-4 border-b border-rule-light py-3 no-underline"
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
        </li>
      ))}
    </ol>
  );
}
