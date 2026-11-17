/**
 * Server-side reads, cached with Next's `use cache` so pages keep a prerendered shell.
 * Errors are not cached: a failed call throws and the next request tries again.
 */
import { cacheLife } from "next/cache";

import { getProduct, getStats, type ProductResponse, type StatsOverview } from "./api";

export async function cachedStats(): Promise<StatsOverview> {
  "use cache";
  cacheLife("hours");
  return getStats();
}

export async function cachedProduct(code: string): Promise<ProductResponse> {
  "use cache";
  cacheLife("hours");
  return getProduct(code);
}
