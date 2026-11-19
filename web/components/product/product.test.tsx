import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { Additive, Ingredient, Nutrition } from "@/lib/api";
import { formatEnergy, formatGrams, formatShare } from "@/lib/format";

// motion reads prefers-reduced-motion once at load, so the hook is mocked to switch it per test.
const motionPreference = vi.hoisted(() => ({ reduced: false }));
vi.mock("motion/react", async (original) => ({
  ...(await original<typeof import("motion/react")>()),
  useReducedMotion: () => motionPreference.reduced,
}));

const { AdditiveList } = await import("./additive-list");
const { IngredientList } = await import("./ingredient-list");
const { NutritionPanel, PIECES, PRINT_END, startOf } = await import("./nutrition-panel");

afterEach(() => {
  cleanup();
  motionPreference.reduced = false;
});

const full: Nutrition = {
  energy_kcal_100g: 376,
  sugars_100g: 4.4,
  salt_100g: 1.2,
  fat_100g: 6.7,
  saturated_fat_100g: 1.2,
  fiber_100g: 10,
  proteins_100g: 12.4,
};

describe("NutritionPanel", () => {
  test("rows follow US label order with formatted values", () => {
    render(<NutritionPanel nutrition={full} />);
    const panel = screen.getByRole("region", { name: "Nutrition Facts" });
    const labels = Array.from(panel.querySelectorAll("[data-row] > span:first-child")).map(
      (el) => el.textContent,
    );
    expect(labels).toEqual(["Energy", "Fat", "Saturated fat", "Salt", "Fiber", "Sugars", "Protein"]);
    expect(within(panel).getByText("376 kcal")).toBeTruthy();
    expect(within(panel).getByText("4.4 g")).toBeTruthy();
    expect(within(panel).getByText("10 g")).toBeTruthy();
  });

  test("missing values say so, in a row and in a sentence", () => {
    render(<NutritionPanel nutrition={{ ...full, sugars_100g: null, fiber_100g: null }} />);
    expect(screen.getAllByText("Not listed")).toHaveLength(2);
    expect(
      screen.getByText("Open Food Facts has no fiber or sugar value for this product."),
    ).toBeTruthy();
  });

  test("rules open and close the panel heavy, medium between groups", () => {
    const rules = PIECES.filter((p) => p.kind === "rule").map((p) => (p.kind === "rule" ? p.weight : ""));
    expect(rules[0]).toBe("heavy");
    expect(rules[rules.length - 1]).toBe("heavy");
    expect(rules.filter((w) => w === "medium")).toHaveLength(4);
  });

  test("the print finishes inside DESIGN.md's 900 ms", () => {
    const last = startOf(PIECES.length - 1) + 0.24;
    const chipSettles = 0.45 + 0.42;
    expect(Math.max(last, chipSettles)).toBeLessThanOrEqual(PRINT_END);
    // Rows wipe in 30 ms apart.
    expect(startOf(3) - startOf(2)).toBeCloseTo(0.03);
  });

  test("animates by default and is complete and still under reduced motion", () => {
    const { unmount } = render(<NutritionPanel nutrition={full} />);
    expect(screen.getByRole("region").getAttribute("data-print")).toBe("animated");
    unmount();
    motionPreference.reduced = true;
    render(<NutritionPanel nutrition={full} />);
    const panel = screen.getByRole("region");
    expect(panel.getAttribute("data-print")).toBe("static");
    expect(panel.innerHTML).not.toContain("clip-path");
    expect(within(panel).getByText("376 kcal")).toBeTruthy();
  });
});

describe("AdditiveList", () => {
  const additives: Additive[] = [
    {
      additive_id: "en:e330",
      e_number: "E330",
      name: "Citric acid",
      function: "Antioxidant, sequestrant",
      explainer: null,
      flagged: false,
    },
    { additive_id: "en:e999", e_number: "E999", name: "Quillaia extract", function: null, explainer: null, flagged: false },
  ];

  test("rows expand to show what the additive does", () => {
    render(<AdditiveList additives={additives} />);
    const button = screen.getByRole("button", { name: /E330\s*Citric acid/ });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Used as: antioxidant, sequestrant.")).toBeTruthy();
  });

  test("an open row links to the additive's guide page", () => {
    render(<AdditiveList additives={additives} />);
    fireEvent.click(screen.getByRole("button", { name: /E330\s*Citric acid/ }));
    expect(screen.getByRole("link", { name: "More about Citric acid" }).getAttribute("href")).toBe(
      "/additives/e330",
    );
  });

  test("an additive with no listed function says so", () => {
    render(<AdditiveList additives={additives} />);
    fireEvent.click(screen.getByRole("button", { name: /Quillaia extract/ }));
    expect(screen.getByText("Open Food Facts does not list what it is used for.")).toBeTruthy();
  });

  test("AI explainers carry the AI note", () => {
    render(
      <AdditiveList
        additives={[{ ...additives[0], explainer: { text: "An acid from citrus.", ai_generated: true } }]}
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("An acid from citrus.")).toBeTruthy();
    expect(screen.getByText("Written by AI from Open Food Facts data.")).toBeTruthy();
  });
});

describe("IngredientList", () => {
  const ingredients: Ingredient[] = [
    { ingredient_id: "en:oat", name: "Oats", rank: 1, explainer: { text: "Whole grain oats, rolled.", ai_generated: true } },
    { ingredient_id: "en:quillaia", name: "Quillaia", rank: 2, explainer: null },
  ];

  test("keeps label order with ranks", () => {
    render(<IngredientList ingredients={ingredients} />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.textContent?.replace("⌄", "").trim())).toEqual(["1Oats", "2Quillaia"]);
  });

  test("only ingredients with an explainer expand, and show the AI note", () => {
    render(<IngredientList ingredients={ingredients} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0].getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(buttons[0]);
    expect(buttons[0].getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Whole grain oats, rolled.")).toBeTruthy();
    expect(screen.getByText("Written by AI from Open Food Facts data.")).toBeTruthy();
  });
});

describe("format", () => {
  test.each([
    [0, "0 g"],
    [0.01, "<0.1 g"],
    [0.06, "0.1 g"],
    [2.5, "2.5 g"],
    [3, "3 g"],
    [12.4, "12 g"],
  ])("formatGrams(%s) is %s", (value, text) => {
    expect(formatGrams(value)).toBe(text);
  });

  test("energy and shares", () => {
    expect(formatEnergy(375.6)).toBe("376 kcal");
    expect(formatShare(1, 3)).toBe("33%");
    expect(formatShare(1, 1000)).toBe("<1%");
  });
});

describe("SwapList and no-swap reasons", async () => {
  const { SwapList } = await import("./swap-list");
  const { noSwapsReason } = await import("@/lib/copy");
  const swap = {
    product: {
      code: "0016000124790",
      name: "Plain Cheerios",
      brand: "General Mills",
      category_main: "breakfast-cereals",
      nutriscore_grade: "a" as const,
      nova_group: 3 as const,
      image_url: null,
    },
    reason: "Nutri-Score A instead of C · no additives instead of 2 · none flagged by Open Food Facts",
    additive_count: 0,
  };

  test("each swap links to its product with name, brand, grade and reason", () => {
    render(<SwapList swaps={[swap]} from="0016000275287" />);
    const link = screen.getByRole("link", { name: /^Plain Cheerios/ });
    expect(link.getAttribute("href")).toBe("/product/0016000124790");
    expect(within(link).getByText("General Mills")).toBeTruthy();
    expect(within(link).getByText(swap.reason)).toBeTruthy();
    expect(within(link).getByRole("img", { name: "Nutri-Score A" })).toBeTruthy();
  });

  test("each swap also compares with the product being viewed, beside its link", () => {
    const { container } = render(<SwapList swaps={[swap]} from="0016000275287" />);
    const compare = screen.getByRole("link", { name: "Compare with Plain Cheerios" });
    expect(compare.getAttribute("href")).toBe("/compare?codes=0016000275287,0016000124790");
    expect(container.querySelector("a a")).toBeNull(); // links never nest
  });

  test("an empty list says which rule left nothing", () => {
    expect(noSwapsReason({ category_main: "other", nutriscore_grade: "d" })).toMatch(/no category/);
    expect(noSwapsReason({ category_main: null, nutriscore_grade: "d" })).toMatch(/no category/);
    expect(noSwapsReason({ category_main: "cheese", nutriscore_grade: null })).toMatch(/no Nutri-Score/);
    expect(noSwapsReason({ category_main: "cheese", nutriscore_grade: "a" })).toMatch(/already scores/);
    expect(noSwapsReason({ category_main: "cheese", nutriscore_grade: "d" })).toMatch(/No similar product/);
  });
});
