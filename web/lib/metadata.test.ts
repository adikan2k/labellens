import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test, vi } from "vitest";

vi.mock("next/cache", () => ({ cacheLife: () => {} }));
vi.mock("@/lib/cached", () => ({ cachedProduct: vi.fn(), cachedSwaps: vi.fn() }));

import { generateMetadata } from "@/app/product/[code]/page";
import { cachedProduct } from "@/lib/cached";
import type { ProductResponse } from "@/lib/api";

import {
  HOME_TITLE,
  PREVIEW_ALT,
  ROOT_TITLE,
  SITE_URL,
  productDescription,
  productTitle,
  social,
} from "./metadata";

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
    const title = "Lucky Charms (Lucky Charms)";
    const description = "Nutrition, additives and ingredients for Lucky Charms, from Open Food Facts.";
    await expect(metadataFor("0016000123991")).resolves.toEqual({
      title,
      description,
      ...social(title, description),
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

describe("link previews", () => {
  const image = { url: "/og.png", width: 1200, height: 630, alt: PREVIEW_ALT };

  test("a pasted link gets a title, a line, the site name and the large image", () => {
    expect(social("A title", "A line")).toEqual({
      openGraph: {
        type: "website",
        siteName: "LabelLens",
        locale: "en_US",
        title: "A title",
        description: "A line",
        images: [image],
      },
      twitter: {
        card: "summary_large_image",
        title: "A title",
        description: "A line",
        images: [image],
      },
    });
  });

  test("the preview image exists at the size the tags give", () => {
    // Vitest runs from web/.
    const png = readFileSync(resolve(process.cwd(), "public", "og.png"));
    // PNG signature, then the IHDR chunk: width and height as big-endian integers.
    expect(png.subarray(1, 4).toString("ascii")).toBe("PNG");
    expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([1200, 630]);
    expect(existsSync(resolve(process.cwd(), "..", "docs/design/og/og.html"))).toBe(true);
  });

  test("image addresses are made absolute against the public site", () => {
    expect(SITE_URL).toBe("https://labellens-beige.vercel.app");
  });
});
