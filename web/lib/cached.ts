/**
 * Server-side reads, cached with Next's `use cache` so pages keep a prerendered shell.
 *
 * Errors are not cached: a failed call throws and the next request tries again. A thrown error
 * also loses its class on the way out of a cached function in a production build, so callers
 * cannot tell an ApiError's status from it. "Not found" is therefore a value (null), never an
 * exception; anything thrown means the API or database is unavailable.
 */
import { cacheLife } from "next/cache";

import {
  ApiError,
  getProduct,
  getStats,
  getSwaps,
  type ProductResponse,
  type StatsOverview,
  type SwapsResponse,
} from "./api";

export async function cachedStats(): Promise<StatsOverview> {
  "use cache";
  cacheLife("hours");
  return getStats();
}

/** The product, or null when this snapshot has no product with that barcode. */
export async function cachedProduct(code: string): Promise<ProductResponse | null> {
  "use cache";
  cacheLife("hours");
  try {
    return await getProduct(code);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** Better swaps for a product. Throws when the API is unavailable (not cached). */
export async function cachedSwaps(code: string): Promise<SwapsResponse> {
  "use cache";
  cacheLife("hours");
  return getSwaps(code);
}
