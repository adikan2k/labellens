import type { Metadata } from "next";
import Link from "next/link";

import { Rule } from "@/components/label/primitives";
import { NOT_FOUND_TITLE } from "@/lib/metadata";

export const metadata: Metadata = { title: NOT_FOUND_TITLE };

export default function NotFound() {
  return (
    <div className="mx-auto w-full max-w-measure px-4 pt-16 pb-16">
      <h1 className="type-page pb-6">{NOT_FOUND_TITLE}</h1>
      <Rule weight="heavy" />
      <p className="type-body pt-4">
        There is nothing at this address. <Link href="/">Search for a product</Link> by name,
        brand or barcode, or open the <Link href="/dashboard">dashboard</Link>.
      </p>
    </div>
  );
}
