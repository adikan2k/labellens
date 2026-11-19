import type { Metadata } from "next";
import { Suspense } from "react";

import { BasketView } from "@/components/basket/basket-view";
import { Rule } from "@/components/label/primitives";
import { parseShared } from "@/lib/basket";
import { BASKET } from "@/lib/copy";

export const metadata: Metadata = {
  title: BASKET.title,
  description: "The products you're thinking of buying, looked at together, with better swaps.",
};

/** Not async: the shared barcodes are read inside the Suspense boundary, so the shell prerenders. */
export default function BasketPage({ searchParams }: PageProps<"/basket">) {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <div className="max-w-measure">
        <h1 className="type-title pb-4">{BASKET.title}</h1>
        <Rule weight="heavy" />
        <p className="type-body pt-4">{BASKET.intro}</p>
      </div>
      <Suspense fallback={null}>
        {searchParams.then(({ codes }) => (
          <BasketView shared={parseShared(typeof codes === "string" ? codes : null)} />
        ))}
      </Suspense>
    </div>
  );
}
