/**
 * Real 404s for unknown barcodes.
 *
 * With Cache Components the product page sends its prerendered shell (and a 200) before the
 * product lookup runs, so a notFound() in the page can only render the not-found label, never
 * change the status. This proxy asks the API first and rewrites a barcode it does not have to
 * /product/missing, which 404s while it prerenders. Anything else (a product, the API asleep or
 * slow) passes through to the page, which handles it as before.
 */
import { NextResponse, type NextRequest } from "next/server";

import { API_URL } from "@/lib/api";

const TIMEOUT_MS = 2000;
const KNOWN_LIMIT = 5000;

/** Barcodes this instance has seen the API return, so prefetches and repeat views skip the call. */
const known = new Set<string>();

export type ProductCheck = "found" | "missing" | "unknown";

/** Whether the API has this barcode. "unknown" when it could not say in time. */
export async function checkProduct(code: string, fetcher: typeof fetch = fetch): Promise<ProductCheck> {
  if (known.has(code)) return "found";
  try {
    const response = await fetcher(`${API_URL}/products/${encodeURIComponent(code)}`, {
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    await response.body?.cancel();
    if (response.status === 404) return "missing";
    if (response.ok) {
      if (known.size >= KNOWN_LIMIT) known.clear();
      known.add(code);
      return "found";
    }
    return "unknown";
  } catch {
    return "unknown";
  }
}

export async function proxy(request: NextRequest) {
  const code = request.nextUrl.pathname.split("/")[2];
  if (!code || code === "missing") return NextResponse.next();
  if ((await checkProduct(decodeURIComponent(code))) !== "missing") return NextResponse.next();
  return NextResponse.rewrite(new URL("/product/missing", request.url));
}

export const config = {
  matcher: "/product/:code",
};
