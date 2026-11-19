"use client";

import Link from "next/link";
import { useState } from "react";

import { GradeChip } from "@/components/label/primitives";
import { NutritionPanel } from "@/components/product/nutrition-panel";
import type { Product } from "@/lib/api";
import { SPECIMEN } from "@/lib/copy";

import { Barcode } from "./barcode";

/**
 * The home page's specimen (DESIGN.md, Home): a real product's label, printing in, with its
 * real barcode. "Next label" cycles the products; each new one prints in again.
 */
export function Specimen({ products }: { products: Product[] }) {
  const [index, setIndex] = useState(0);
  if (products.length === 0) return null;
  const product = products[index % products.length];
  return (
    <section aria-label={SPECIMEN.label} className="mx-auto w-full max-w-[22rem]">
      {/* A white sticker on the warm page; the Nutrition Facts panel inside has the border. */}
      <div className="rotate-[2deg] bg-paper px-4 pt-4 pb-3">
        <div className="flex items-start justify-between gap-3 pb-3">
          <p className="min-w-0">
            <Link
              href={`/product/${product.code}`}
              className="type-data-value block break-words no-underline hover:underline"
            >
              {product.name}
            </Link>
            <span className="type-small block text-ink-muted">{product.brand}</span>
          </p>
          <GradeChip grade={product.nutriscore_grade} />
        </div>
        <NutritionPanel key={product.code} nutrition={product.nutrition} />
        <Barcode code={product.code} className="pt-4" />
      </div>
      {products.length > 1 && (
        <p className="flex items-baseline justify-between gap-4 pt-6">
          <span className="type-small text-ink-muted">{SPECIMEN.caption}</span>
          <button
            type="button"
            className="type-data-value shrink-0 cursor-pointer underline underline-offset-2"
            onClick={() => setIndex((i) => i + 1)}
          >
            {SPECIMEN.next}
          </button>
        </p>
      )}
    </section>
  );
}
