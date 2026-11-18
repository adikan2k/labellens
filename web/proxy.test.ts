import { NextRequest } from "next/server";
import { describe, expect, test, vi } from "vitest";

import { checkProduct, config, proxy } from "./proxy";

function responding(status: number) {
  return vi.fn(async () => new Response(status === 200 ? "{}" : null, { status }));
}

describe("checkProduct", () => {
  test("a 404 from the API means missing", async () => {
    await expect(checkProduct("0000000000001", responding(404))).resolves.toBe("missing");
  });

  test("a product is found, and remembered so the API is asked once", async () => {
    const fetcher = responding(200);
    await expect(checkProduct("0016000123991", fetcher)).resolves.toBe("found");
    await expect(checkProduct("0016000123991", fetcher)).resolves.toBe("found");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  test("an API that is waking up or unreachable is unknown, so the page decides", async () => {
    await expect(checkProduct("0000000000002", responding(503))).resolves.toBe("unknown");
    const failing = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    await expect(checkProduct("0000000000003", failing)).resolves.toBe("unknown");
  });
});

describe("proxy", () => {
  test("runs only on product pages", () => {
    expect(config.matcher).toBe("/product/:code");
  });

  test("rewrites an unknown barcode to the route that 404s", async () => {
    vi.stubGlobal("fetch", responding(404));
    const response = await proxy(new NextRequest("https://labellens.test/product/0000000000004"));
    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "https://labellens.test/product/missing",
    );
    vi.unstubAllGlobals();
  });

  test("lets a real product through", async () => {
    vi.stubGlobal("fetch", responding(200));
    const response = await proxy(new NextRequest("https://labellens.test/product/0016000169678"));
    expect(response.headers.get("x-middleware-rewrite")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
    vi.unstubAllGlobals();
  });
});
