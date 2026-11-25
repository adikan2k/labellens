import Link from "next/link";

import { Rule } from "@/components/label/primitives";
import { PRODUCT_NOT_FOUND_TITLE } from "@/lib/metadata";

/** Shown for a barcode this snapshot does not have, whether the proxy or the page found out. */
export function ProductNotFound() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
      <h1 className="type-page pb-6">{PRODUCT_NOT_FOUND_TITLE}</h1>
      <Rule weight="heavy" />
      <p className="type-body pt-4">
        It is not in this Open Food Facts snapshot of US products, or it has no name.{" "}
        <Link href="/">Search by name or brand</Link> instead.
      </p>
    </div>
  );
}
