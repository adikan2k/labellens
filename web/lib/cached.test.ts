import { afterEach, describe, expect, test, vi } from "vitest";

// Outside a Next server, `use cache` is a plain string and cacheLife has nothing to configure.
vi.mock("next/cache", () => ({ cacheLife: () => {} }));

import { cachedProduct } from "./cached";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    })),
  );
}

// A production build strips the class from errors thrown out of a `use cache` function, so the
// product page cannot read a 404 from an exception. Not found has to be a value.
describe("cachedProduct", () => {
  test("a product the snapshot does not have is null, not an error", async () => {
    stubFetch(404, { detail: "No product with barcode 0000000000000 in this snapshot." });
    await expect(cachedProduct("0000000000000")).resolves.toBeNull();
  });

  test("an unavailable API still throws, so the failure is not cached", async () => {
    stubFetch(503, { detail: "waking up" });
    await expect(cachedProduct("0016000275287")).rejects.toThrow();
  });

  test("a found product is returned as the API sent it", async () => {
    const body = { product: { code: "0016000275287", name: "Cheerios" }, source: {} };
    stubFetch(200, body);
    await expect(cachedProduct("0016000275287")).resolves.toEqual(body);
  });
});
