import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PRODUCT_NOT_FOUND_TITLE } from "@/lib/metadata";

export const metadata: Metadata = { title: PRODUCT_NOT_FOUND_TITLE };

/**
 * The proxy (web/proxy.ts) rewrites an unknown barcode here. notFound() runs while the page
 * prerenders, before any response starts, so this route is served with a real 404 and the
 * product not-found label beside it. The product page's own notFound() runs inside Suspense,
 * after the prerendered shell has sent a 200, so it alone cannot.
 */
export default function MissingProduct(): never {
  notFound();
}
