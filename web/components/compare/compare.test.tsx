import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import type { Product } from "@/lib/api";

import { CompareTable } from "./compare-table";

afterEach(cleanup);

const product = (over: Partial<Product>): Product => ({
  code: "0016000275287",
  name: "Cheerios",
  brand: "General Mills",
  category_main: "breakfast-cereals",
  nutriscore_grade: "a",
  nova_group: 1,
  image_url: null,
  category_name: "Breakfast cereals",
  category_source: "off_tags",
  completeness: 0.9,
  nutrition: {
    energy_kcal_100g: 376,
    sugars_100g: 4.4,
    salt_100g: 1.2,
    fat_100g: 6.7,
    saturated_fat_100g: 1.2,
    fiber_100g: 10,
    proteins_100g: 12.4,
  },
  additives: [
    { additive_id: "en:e306", e_number: "E306", name: "Tocopherols", function: null, explainer: null },
  ],
  ingredients: [],
  off_url: "https://world.openfoodfacts.org/product/0016000275287",
  in_graph: true,
  ...over,
});

const cheerios = product({});
const honeyNut = product({
  code: "0016000169685",
  name: "Honey Nut Cheerios",
  nutriscore_grade: "c",
  nova_group: 4,
  nutrition: { ...cheerios.nutrition, energy_kcal_100g: 393, sugars_100g: 33, fiber_100g: null },
  additives: [
    { additive_id: "en:e306", e_number: "E306", name: "Tocopherols", function: null, explainer: null },
    { additive_id: "en:e330", e_number: "E330", name: "Citric acid", function: null, explainer: null },
  ],
});

describe("CompareTable", () => {
  test("a table with a column per product, linked, with brand and grade", () => {
    render(<CompareTable a={cheerios} b={honeyNut} />);
    const table = screen.getByRole("table");
    const heads = within(table).getAllByRole("columnheader");
    expect(heads.map((h) => within(h).getByRole("link").getAttribute("href"))).toEqual([
      "/product/0016000275287",
      "/product/0016000169685",
    ]);
    expect(within(heads[1]).getByRole("img", { name: "Nutri-Score C" })).toBeTruthy();
  });

  test("rows in label order, the second's difference under its value", () => {
    render(<CompareTable a={cheerios} b={honeyNut} />);
    const rows = within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent);
    expect(rows).toEqual([
      "Energy", "Fat", "Saturated fat", "Salt", "Fiber", "Sugars", "Protein",
      "Processing", "Additives", "Ingredients",
    ]); // prettier-ignore
    const sugars = screen.getByRole("rowheader", { name: "Sugars" }).closest("tr")!;
    expect(within(sugars).getByText("33 g")).toBeTruthy();
    expect(within(sugars).getByText("29 g more")).toBeTruthy();
    const energy = screen.getByRole("rowheader", { name: "Energy" }).closest("tr")!;
    expect(within(energy).getByText("17 kcal more")).toBeTruthy();
  });

  test("a missing value says Not listed and has no difference; no cell is blank", () => {
    render(<CompareTable a={cheerios} b={honeyNut} />);
    const fiber = screen.getByRole("rowheader", { name: "Fiber" }).closest("tr")!;
    expect(within(fiber).getByText("Not listed")).toBeTruthy();
    expect(fiber.querySelector("[data-difference]")).toBeNull();
    for (const cell of screen.getByRole("table").querySelectorAll("tbody tr:not([aria-hidden]) td")) {
      expect(cell.textContent?.trim()).not.toBe("");
    }
  });

  test("never says better or worse", () => {
    const { container } = render(<CompareTable a={cheerios} b={honeyNut} />);
    expect(container.textContent).not.toMatch(/better|worse|healthier/i);
  });

  test("additives split into both, only in each", () => {
    render(<CompareTable a={cheerios} b={honeyNut} />);
    const section = screen.getByRole("region", { name: "Additives" });
    expect(within(section).getByText("In both").nextElementSibling?.textContent).toBe("E306 Tocopherols");
    expect(within(section).getByText("Only in Cheerios").nextElementSibling?.textContent).toBe("None");
    expect(
      within(section).getByText("Only in Honey Nut Cheerios").nextElementSibling?.textContent,
    ).toBe("E330 Citric acid");
  });
});
