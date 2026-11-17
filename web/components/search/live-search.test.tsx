import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, type SearchResponse } from "@/lib/api";
import { NO_MATCH, WAKING_UP } from "@/lib/copy";

const searchProducts = vi.fn();
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  searchProducts: (...args: unknown[]) => searchProducts(...args),
}));

const { LiveSearch } = await import("./live-search");

const cheerios: SearchResponse = {
  query: "cheerios",
  source: {
    name: "Open Food Facts",
    url: "https://world.openfoodfacts.org",
    licence: "ODbL-1.0",
    licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
    snapshot_date: "2026-11-17",
  },
  results: [
    {
      code: "0016000275263",
      name: "Cheerios",
      brand: "General Mills",
      category_main: "breakfast-cereals",
      nutriscore_grade: "c",
      nova_group: 4,
      image_url: null,
      match: "name",
    },
  ],
};

beforeEach(() => {
  vi.useFakeTimers();
  searchProducts.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

async function type(text: string) {
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: text } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(200);
  });
}

describe("LiveSearch", () => {
  test("puts the live product count in a placeholder short enough for a phone", () => {
    render(<LiveSearch productCount={985260} />);
    expect(screen.getByRole("searchbox").getAttribute("placeholder")).toBe(
      "Search 985,260 US products",
    );
    // How to search sits under the box, where it is never cut off.
    expect(screen.getByText(/Name, brand or barcode\. Try:/)).toBeTruthy();
  });

  test("shows results as label rows linking to the product", async () => {
    searchProducts.mockResolvedValue(cheerios);
    render(<LiveSearch productCount={null} />);
    await type("cheerios");

    expect(searchProducts).toHaveBeenCalledWith("cheerios", expect.objectContaining({ limit: 10 }));
    const link = screen.getByRole("link", { name: /Cheerios/ });
    expect(link.getAttribute("href")).toBe("/product/0016000275263");
    expect(screen.getByRole("img", { name: "Nutri-Score C" })).toBeTruthy();
    expect(screen.getByText("1 product found")).toBeTruthy();
  });

  test("waits for typing to pause and cancels the stale request", async () => {
    searchProducts.mockResolvedValue(cheerios);
    render(<LiveSearch productCount={null} />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "che" } });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });
    await type("cheerios");
    expect(searchProducts).toHaveBeenCalledTimes(1);
    expect(searchProducts.mock.calls[0][0]).toBe("cheerios");
  });

  test("says how to search differently when nothing matches", async () => {
    searchProducts.mockResolvedValue({ ...cheerios, results: [] });
    render(<LiveSearch productCount={null} />);
    await type("zzqx");
    expect(screen.getByText(NO_MATCH)).toBeTruthy();
  });

  test("says the search is waking up and offers a retry", async () => {
    searchProducts.mockRejectedValueOnce(new ApiError(503, WAKING_UP)).mockResolvedValue(cheerios);
    render(<LiveSearch productCount={null} />);
    await type("cheerios");
    expect(screen.getByText(WAKING_UP)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(screen.getByRole("link", { name: /Cheerios/ })).toBeTruthy();
  });

  test("example buttons fill the search", async () => {
    searchProducts.mockResolvedValue(cheerios);
    render(<LiveSearch productCount={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Oreo" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect((screen.getByRole("searchbox") as HTMLInputElement).value).toBe("Oreo");
    expect(searchProducts.mock.calls[0][0]).toBe("Oreo");
  });
});
