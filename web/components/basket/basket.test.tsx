import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { Product, Swap } from "@/lib/api";
import { BASKET } from "@/lib/copy";

const getProduct = vi.fn();
const getSwaps = vi.fn();
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  getProduct: (...args: unknown[]) => getProduct(...args),
  getSwaps: (...args: unknown[]) => getSwaps(...args),
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const basket = await import("@/lib/basket");
const { AddToBasket, BasketLink } = await import("./add-to-basket");
const { BasketView } = await import("./basket-view");

const additive = (id: string, e: string, name: string, flagged = false) => ({
  additive_id: id,
  e_number: e,
  name,
  function: null,
  explainer: null,
  flagged,
});

function product(code: string, over: Partial<Product> = {}): Product {
  return {
    code,
    name: `Product ${code}`,
    brand: "Brand",
    category_main: "breakfast-cereals",
    nutriscore_grade: "d",
    nova_group: 4,
    image_url: null,
    category_name: null,
    category_source: null,
    completeness: null,
    nutrition: {
      energy_kcal_100g: 400,
      sugars_100g: 30,
      salt_100g: 1,
      fat_100g: 10,
      saturated_fat_100g: 2,
      fiber_100g: 3,
      proteins_100g: 6,
    },
    additives: [],
    ingredients: [],
    off_url: "",
    in_graph: false,
    ...over,
  };
}

const source = { name: "Open Food Facts" } as never;

beforeEach(() => {
  localStorage.clear();
  getProduct.mockReset();
  getSwaps.mockReset();
});
afterEach(cleanup);

describe("the store", () => {
  test("keeps barcodes only, no repeats, thirty at most", () => {
    expect(basket.cleanCodes(["1", "1", "x", 2, "3"])).toEqual(["1", "3"]);
    expect(basket.cleanCodes(Array.from({ length: 40 }, (_, i) => String(i)))).toHaveLength(30);
    expect(basket.cleanCodes("not a list")).toEqual([]);
    localStorage.setItem(basket.BASKET_KEY, "{broken");
    expect(basket.readBasket()).toEqual([]);
  });

  test("adds, removes and swaps in place", () => {
    basket.addToBasket("111");
    basket.addToBasket("222");
    basket.addToBasket("111");
    expect(basket.readBasket()).toEqual(["111", "222"]);
    basket.replaceInBasket("111", "999");
    expect(basket.readBasket()).toEqual(["999", "222"]);
    basket.removeFromBasket("222");
    expect(basket.readBasket()).toEqual(["999"]);
  });

  test("a shared link holds barcodes and nothing else", () => {
    expect(basket.shareHref(["111", "222"])).toBe("/basket?codes=111,222");
    expect(basket.parseShared("111, 222,abc")).toEqual(["111", "222"]);
    expect(basket.parseShared(null)).toBeNull();
  });
});

describe("the summary", () => {
  test("counts grades, processing, high-in flags and additives; flagged additives first", () => {
    const summary = basket.summarise([
      product("1", { nutriscore_grade: "a", nova_group: 1, nutrition: { ...product("1").nutrition, sugars_100g: 2 } }),
      product("2", { additives: [additive("en:e330", "E330", "Citric acid"), additive("en:e250", "E250", "Sodium nitrite", true)] }),
      product("3", { nutriscore_grade: null, additives: [additive("en:e330", "E330", "Citric acid")] }),
    ]);
    expect(summary.count).toBe(3);
    expect(summary.grades).toEqual({ a: 1, b: 0, c: 0, d: 1, e: 0 });
    expect(summary.ungraded).toBe(1);
    expect(summary.ultraProcessed).toBe(2);
    expect(summary.high).toEqual([{ nutrient: "sugars_100g", name: "sugars", count: 2 }]);
    expect(summary.additives.map((a) => [a.additive.e_number, a.products.length])).toEqual([
      ["E250", 1],
      ["E330", 2],
    ]);
    expect(summary.flaggedAdditives).toBe(1);
  });
});

describe("Add to my basket", () => {
  test("adds the product, then links to the basket; the header shows the count", () => {
    render(
      <>
        <AddToBasket code="111" />
        <BasketLink />
      </>,
    );
    expect(screen.queryByRole("link", { name: /My basket/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: BASKET.add }));
    expect(basket.readBasket()).toEqual(["111"]);
    expect(screen.getByRole("link", { name: BASKET.added }).getAttribute("href")).toBe("/basket");
    expect(screen.getByRole("link", { name: "My basket (1)" })).toBeTruthy();
  });

  test("a full basket says so instead of adding", () => {
    basket.writeBasket(Array.from({ length: 30 }, (_, i) => String(1000 + i)));
    render(<AddToBasket code="111" />);
    fireEvent.click(screen.getByRole("button", { name: BASKET.add }));
    expect(screen.getByRole("status").textContent).toBe(BASKET.full(30));
    expect(basket.readBasket()).not.toContain("111");
  });
});

describe("the basket page", () => {
  test("empty, it invites a start", () => {
    render(<BasketView shared={null} />);
    expect(screen.getByRole("heading", { name: BASKET.emptyTitle })).toBeTruthy();
  });

  test("shows the products together, and a swap replaces the item", async () => {
    basket.writeBasket(["111", "222"]);
    getProduct.mockImplementation(async (code: string) => ({ product: product(code), source }));
    const swap: Swap = {
      product: { ...product("333"), name: "Plain Oats", nutriscore_grade: "a" },
      reason: "Nutri-Score A instead of D",
      additive_count: 0,
    };
    getSwaps.mockImplementation(async (code: string) => ({ code, swaps: code === "111" ? [swap] : [], source }));
    render(<BasketView shared={null} />);
    const summary = await screen.findByRole("region", { name: "The basket together" });
    await waitFor(() => expect(summary.textContent).toContain("2 products · 2 ultra-processed"));
    expect(summary.textContent).toContain("High in sugars: 2");
    const bar = within(summary).getByRole("list", { name: BASKET.gradeBarLabel });
    expect(within(bar).getAllByRole("listitem")).toHaveLength(1); // both are D

    const swapButton = await screen.findByRole("button", { name: "Swap Product 111 for Plain Oats" });
    act(() => swapButton.click());
    expect(basket.readBasket()).toEqual(["333", "222"]);
  });

  test("a shared basket is read-only until saved", async () => {
    getProduct.mockImplementation(async (code: string) => ({ product: product(code), source }));
    render(<BasketView shared={["444"]} />);
    await screen.findByRole("link", { name: "Product 444" });
    expect(screen.queryByRole("button", { name: /Remove/ })).toBeNull();
    expect(getSwaps).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: BASKET.save }));
    expect(basket.readBasket()).toEqual(["444"]);
    expect(push).toHaveBeenCalledWith("/basket");
  });

  test("with rules set, it counts who meets them and names each miss", async () => {
    const { writePreferences, NO_PREFERENCES } = await import("@/lib/preferences");
    writePreferences({ ...NO_PREFERENCES, limits: { sugars_100g: 10 }, minGrade: "c" });
    basket.writeBasket(["111", "222"]);
    getProduct.mockImplementation(async (code: string) => ({
      product: code === "111" ? product(code, { nutriscore_grade: "b", nutrition: { ...product(code).nutrition, sugars_100g: 5 } }) : product(code),
      source,
    }));
    getSwaps.mockResolvedValue({ swaps: [], source });
    render(<BasketView shared={null} />);
    expect(await screen.findByRole("link", { name: "1 of 2 meet all your rules" })).toBeTruthy();
    expect(screen.getByText("Misses your rules: sugars, Nutri-Score")).toBeTruthy();
  });

  test("a barcode no longer in the data says so and can be removed", async () => {
    basket.writeBasket(["555"]);
    getProduct.mockRejectedValue(new Error("404"));
    render(<BasketView shared={null} />);
    expect(await screen.findByText(BASKET.missing("555"))).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove 555" }));
    expect(basket.readBasket()).toEqual([]);
  });
});
