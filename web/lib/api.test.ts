import { afterEach, describe, expect, test, vi } from "vitest";

import { ApiError, getProduct, searchProducts } from "./api";
import { missingValues, WAKING_UP } from "./copy";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(response: Partial<Response> | Error | DOMException) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    // In jsdom a DOMException is not an Error subclass, so check it separately.
    if (response instanceof Error || response instanceof DOMException) throw response;
    return response as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api client", () => {
  test("search sends q and limit and returns the body", async () => {
    const body = { query: "oreo", results: [], source: {} };
    const fetchMock = stubFetch({ ok: true, json: async () => body });
    await expect(searchProducts("oreo cookies", { limit: 5 })).resolves.toEqual(body);
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/search?q=oreo+cookies&limit=5");
  });

  test("product codes are encoded", async () => {
    const fetchMock = stubFetch({ ok: true, json: async () => ({}) });
    await getProduct("12/34");
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/products/12%2F34");
  });

  test("API errors carry the status and the contract's detail", async () => {
    stubFetch({ ok: false, status: 404, json: async () => ({ detail: "No product with barcode 1." }) });
    const error = await getProduct("1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).message).toBe("No product with barcode 1.");
    expect((error as ApiError).wakingUp).toBe(false);
  });

  test("no response at all reads as waking up", async () => {
    stubFetch(new TypeError("Failed to fetch"));
    const error = (await searchProducts("milk").catch((e: unknown) => e)) as ApiError;
    expect(error.wakingUp).toBe(true);
    expect(error.message).toBe(WAKING_UP);
  });

  test("an aborted request stays an abort", async () => {
    stubFetch(new DOMException("aborted", "AbortError"));
    await expect(searchProducts("milk")).rejects.toMatchObject({ name: "AbortError" });
  });
});

describe("copy", () => {
  test("missing values read as a sentence", () => {
    expect(missingValues([])).toBeNull();
    expect(missingValues(["sugar"])).toBe("Open Food Facts has no sugar value for this product.");
    expect(missingValues(["sugar", "fiber", "salt"])).toBe(
      "Open Food Facts has no sugar, fiber or salt value for this product.",
    );
  });
});
