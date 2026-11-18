/**
 * Typed client for the LabelLens API. Types come from docs/openapi.yaml through
 * `pnpm gen:api`; `pnpm typecheck` fails if lib/api-types.ts is out of date.
 */
import type { components } from "./api-types";
import { WAKING_UP } from "./copy";

type Schemas = components["schemas"];
export type ProductSummary = Schemas["ProductSummary"];
export type SearchResult = Schemas["SearchResult"];
export type SearchResponse = Schemas["SearchResponse"];
export type Product = Schemas["Product"];
export type ProductResponse = Schemas["ProductResponse"];
export type Additive = Schemas["Additive"];
export type Ingredient = Schemas["Ingredient"];
export type Explainer = Schemas["Explainer"];
export type Nutrition = Schemas["Nutrition"];
export type StatsOverview = Schemas["StatsOverview"];
export type CountByKey = Schemas["CountByKey"];
export type Source = Schemas["Source"];
export type NutriscoreGrade = NonNullable<Schemas["NutriscoreGrade"]>;
export type Swap = Schemas["Swap"];
export type SwapsResponse = Schemas["SwapsResponse"];
export type GraphNeighborhood = Schemas["GraphNeighborhood"];
export type GraphNode = Schemas["GraphNode"];
export type GraphEdge = Schemas["GraphEdge"];

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** The API (Cloud Run) or the database (Neon) is starting up from idle. */
  get wakingUp(): boolean {
    return this.status === 503;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch (error) {
    // Checked by name: DOMException is not an Error subclass in every runtime.
    if ((error as { name?: string } | null)?.name === "AbortError") throw error;
    // No response at all: the API is cold-starting or unreachable.
    throw new ApiError(503, WAKING_UP);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as Schemas["Error"] | null;
    throw new ApiError(response.status, body?.detail ?? `Request failed (${response.status}).`);
  }
  return (await response.json()) as T;
}

export function searchProducts(
  q: string,
  options: { limit?: number; signal?: AbortSignal } = {},
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, limit: String(options.limit ?? 10) });
  return request<SearchResponse>(`/search?${params}`, { signal: options.signal });
}

export function getProduct(code: string): Promise<ProductResponse> {
  return request<ProductResponse>(`/products/${encodeURIComponent(code)}`);
}

export function getSwaps(code: string, limit = 5): Promise<SwapsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return request<SwapsResponse>(`/products/${encodeURIComponent(code)}/swaps?${params}`);
}

export function getNeighborhood(
  code: string,
  options: { depth?: 1 | 2; signal?: AbortSignal } = {},
): Promise<GraphNeighborhood> {
  const params = new URLSearchParams({ code, depth: String(options.depth ?? 2) });
  return request<GraphNeighborhood>(`/graph/neighborhood?${params}`, { signal: options.signal });
}

export function getStats(): Promise<StatsOverview> {
  return request<StatsOverview>("/stats/overview");
}
