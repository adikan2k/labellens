import { describe, expect, test, vi } from "vitest";

vi.mock("next/cache", () => ({ cacheLife: () => {} }));
vi.mock("@/lib/cached", () => ({ cachedProduct: vi.fn(), cachedSwaps: vi.fn() }));

import { generateMetadata } from "@/app/product/[code]/page";
import { cachedProduct } from "@/lib/cached";
import type { ProductResponse } from "@/lib/api";

import { HOME_TITLE, ROOT_TITLE, productDescription, productTitle } from "./metadata";

const mockedProduct = vi.mocked(cachedProduct);

function metadataFor(code: string) {
  return generateMetadata({ params: Promise.resolve({ code }), searchParams: Promise.resolve({}) });
}

describe("site titles", () => {
  test("every page below the root gets the LabelLens suffix from one template", () => {
    expect(ROOT_TITLE).toEqual({ default: "LabelLens", template: "%s · LabelLens" });
  });

  test("home has its own title, written in full", () => {
    expect(HOME_TITLE).toBe("What’s in it? · LabelLens");
  });
});

describe("productTitle", () => {
  test("name, then the brand in brackets", () => {
    expect(productTitle({ name: "Lucky Charms", brand: "Lucky Charms" })).toBe(
      "Lucky Charms (Lucky Charms)",
    );
  });

  test("name alone when Open Food Facts has no brand", () => {
    expect(productTitle({ name: "Store oats", brand: null })).toBe("Store oats");
  });

  test("description names the product", () => {
    expect(productDescription({ name: "Cheerios" })).toBe(
      "Nutrition, additives and ingredients for Cheerios, from Open Food Facts.",
    );
  });
});

describe("product page generateMetadata", () => {
  test("a product is titled by name and brand", async () => {
    mockedProduct.mockResolvedValueOnce({
      product: { name: "Lucky Charms", brand: "Lucky Charms" },
    } as ProductResponse);
    await expect(metadataFor("0016000123991")).resolves.toEqual({
      title: "Lucky Charms (Lucky Charms)",
      description: "Nutrition, additives and ingredients for Lucky Charms, from Open Food Facts.",
    });
    expect(mockedProduct).toHaveBeenCalledWith("0016000123991");
  });

  test("an unknown barcode is titled as not found", async () => {
    mockedProduct.mockResolvedValueOnce(null);
    await expect(metadataFor("0000000000000")).resolves.toEqual({
      title: "No product with this barcode",
    });
  });

  test("an unavailable API still gives a title instead of failing the page", async () => {
    mockedProduct.mockRejectedValueOnce(new Error("503"));
    await expect(metadataFor("0016000123991")).resolves.toEqual({ title: "Product label" });
  });
});
