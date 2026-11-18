import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { StatsOverview } from "@/lib/api";
import {
  additiveFinding,
  categorySourceNote,
  largestFinding,
  novaFinding,
  nutriscoreFinding,
  poorGradeFinding,
  sugarFinding,
} from "@/lib/findings";

const preference = vi.hoisted(() => ({ reduced: true }));
vi.mock("motion/react", async (original) => ({
  ...(await original<typeof import("motion/react")>()),
  useReducedMotion: () => preference.reduced,
}));
const { BarChart, DataTable, GradeStacks } = await import("./charts");

afterEach(cleanup);

const stats = {
  product_count: 1000,
  named_product_count: 980,
  brand_count: 10,
  category_count: 26,
  additive_count: 5,
  nutriscore: [
    { key: "a", label: "Nutri-Score A", count: 100 },
    { key: "b", label: "Nutri-Score B", count: 50 },
    { key: "c", label: "Nutri-Score C", count: 50 },
    { key: "d", label: "Nutri-Score D", count: 100 },
    { key: "e", label: "Nutri-Score E", count: 100 },
    { key: null, label: "No Nutri-Score", count: 600 },
  ],
  nova: [
    { key: "1", label: "Unprocessed or minimally processed", count: 20 },
    { key: "4", label: "Ultra-processed foods", count: 80 },
    { key: null, label: "No NOVA group", count: 900 },
  ],
  categories: [
    { key: "cheese", label: "Cheese", count: 30 },
    { key: "sodas", label: "Sodas and soft drinks", count: 70 },
  ],
  category_sources: [
    { key: "model", label: "Suggested by AI", count: 690 },
    { key: "off_tags", label: "From Open Food Facts' category tags", count: 280 },
    { key: null, label: "No category", count: 10 },
  ],
  top_additives: [{ key: "en:e330", label: "E330 Citric acid", count: 400 }],
  nutriscore_by_category: [
    { category_id: "cheese", name: "Cheese", graded_count: 100, grades: { a: 0, b: 0, c: 20, d: 50, e: 30 } },
    { category_id: "sodas", name: "Sodas and soft drinks", graded_count: 200, grades: { a: 10, b: 10, c: 80, d: 50, e: 50 } },
  ],
  median_sugars_by_category: [
    { category_id: "sodas", name: "Sodas and soft drinks", median: 10.6, product_count: 300 },
    { category_id: "candy", name: "Candy and chocolate", median: 48.2, product_count: 500 },
  ],
  source: {
    name: "Open Food Facts",
    url: "https://world.openfoodfacts.org",
    licence: "ODbL-1.0",
    licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
    snapshot_date: "2026-11-17",
  },
} satisfies StatsOverview;

describe("findings are computed from the numbers", () => {
  test("Nutri-Score: share of graded products at C or worse", () => {
    expect(nutriscoreFinding(stats.nutriscore)).toBe("63% of graded US products score C or worse");
  });
  test("NOVA: ultra-processed share of products with a group", () => {
    expect(novaFinding(stats.nova)).toBe("80% of products with a NOVA group are ultra-processed");
  });
  test("largest category and most common additive", () => {
    expect(largestFinding(stats.categories, "category")).toBe(
      "Sodas and soft drinks is the largest category, with 70 products",
    );
    expect(additiveFinding(stats.top_additives)).toBe(
      "E330 Citric acid is in more products than any other additive: 400",
    );
  });
  test("category with the most D and E grades", () => {
    expect(poorGradeFinding(stats)).toBe("Cheese: 80% score D or E, the most of any category");
  });
  test("the category note gives each source's share and leaves out Other", () => {
    expect(categorySourceNote(stats.category_sources)).toBe(
      "29% of products are placed by their Open Food Facts category tags; 70% by AI from the name " +
        "and ingredients, where the tags give none. “Other or unclear” is left out.",
    );
    const tagsOnly = [{ key: "off_tags", label: "", count: 5 }];
    expect(categorySourceNote(tagsOnly)).not.toContain("AI");
  });

  test("category with the highest median sugar", () => {
    expect(sugarFinding(stats)).toBe("Candy and chocolate have the most sugar: a median of 48.2 g per 100 g");
  });
  test("empty data does not invent a finding", () => {
    expect(nutriscoreFinding([])).toBe("No products have a Nutri-Score yet");
    expect(sugarFinding({ ...stats, median_sugars_by_category: [] })).toBe(
      "Not enough sugar values per category yet",
    );
  });
});

describe("charts", () => {
  test("bars scale to the largest value and show their numbers", () => {
    const { container } = render(
      <BarChart
        bars={[
          { label: "Sodas", value: 70, display: "70" },
          { label: "Cheese", value: 35, display: "35" },
        ]}
      />,
    );
    const bars = Array.from(container.querySelectorAll<HTMLElement>("[data-bar]"));
    expect(bars.map((b) => b.style.width)).toEqual(["100%", "50%"]);
    expect(bars.every((b) => b.className.includes("bg-ink"))).toBe(true);
    expect(container.textContent).toContain("70");
  });

  test("Nutri-Score colours only on Nutri-Score bars", () => {
    const { container } = render(
      <BarChart bars={[{ label: "Nutri-Score A", value: 1, display: "1", grade: "a" }]} />,
    );
    expect(container.querySelector("[data-bar]")?.className).toContain("bg-grade-a");
  });

  test("grade stacks split by grade and carry a lettered legend", () => {
    const { container } = render(
      <GradeStacks stacks={[{ label: "Cheese", parts: { a: 0, b: 0, c: 20, d: 50, e: 30 }, total: 100 }]} />,
    );
    expect(container.textContent).toContain("ABCDE");
    const widths = Array.from(container.querySelectorAll<HTMLElement>("[data-bar] > span")).map((s) => s.style.width);
    expect(widths).toEqual(["20%", "50%", "30%"]);
  });

  test("every chart's data is available as a table", () => {
    render(<DataTable caption="Products per grade" headers={["Grade", "Products"]} rows={[["A", "100"]]} />);
    expect(screen.getByText("Show the numbers")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Products per grade" })).toBeTruthy();
    expect(screen.getByRole("rowheader", { name: "A" })).toBeTruthy();
  });
});
