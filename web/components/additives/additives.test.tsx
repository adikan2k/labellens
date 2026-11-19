import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { additiveHref, filterAdditives } from "@/lib/additives";
import type { AdditiveListItem } from "@/lib/api";

import { AdditiveFinder } from "./additive-finder";
import { CategoryBars, ProductRows } from "./guide-parts";

afterEach(cleanup);

const item = (over: Partial<AdditiveListItem>): AdditiveListItem => ({
  additive_id: "en:e330",
  slug: "e330",
  e_number: "E330",
  name: "Citric acid",
  function: "Acidity regulator",
  flagged: false,
  product_count: 100,
  ...over,
});

const LIST = [
  item({}),
  item({ additive_id: "en:e322", slug: "e322", e_number: "E322", name: "Lecithins", product_count: 50 }),
  item({ additive_id: "en:e150d", slug: "e150d", e_number: "E150d", name: "Sulphite ammonia caramel", flagged: true, product_count: 20 }),
  item({ additive_id: "xx:pectin", slug: "xx:pectin", e_number: null, name: "Pectin", function: null, product_count: 5 }),
];

describe("additiveHref", () => {
  test("drops en: and keeps other ids whole", () => {
    expect(additiveHref("en:e330")).toBe("/additives/e330");
    expect(additiveHref("xx:pectin")).toBe("/additives/xx%3Apectin");
  });
});

describe("filterAdditives", () => {
  test("matches the name or the E number, however the E number is written", () => {
    expect(filterAdditives(LIST, "lecith").map((a) => a.name)).toEqual(["Lecithins"]);
    for (const q of ["E 330", "e-330", "e330", "330"]) {
      expect(filterAdditives(LIST, q).map((a) => a.name)).toEqual(["Citric acid"]);
    }
  });

  test("keeps the list's order and handles a missing E number", () => {
    expect(filterAdditives(LIST, "").map((a) => a.name)).toEqual(LIST.map((a) => a.name));
    expect(filterAdditives(LIST, "pect").map((a) => a.name)).toEqual(["Pectin"]);
  });

  test("flagged only", () => {
    expect(filterAdditives(LIST, "", true).map((a) => a.name)).toEqual(["Sulphite ammonia caramel"]);
    expect(filterAdditives(LIST, "citric", true)).toEqual([]);
  });
});

describe("AdditiveFinder", () => {
  test("lists every additive with its count, linking to its page", () => {
    render(<AdditiveFinder additives={LIST} />);
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/additives/e330",
      "/additives/e322",
      "/additives/e150d",
      "/additives/xx%3Apectin",
    ]);
    expect(links[2].textContent).toContain("Flagged by Open Food Facts");
    expect(screen.getByRole("status").textContent).toBe("4 additives");
  });

  test("typing and the flagged box narrow the list, and say how many are shown", () => {
    render(<AdditiveFinder additives={LIST} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Find an additive" }), {
      target: { value: "e3" },
    });
    expect(screen.getAllByRole("link")).toHaveLength(2);
    expect(screen.getByRole("status").textContent).toBe("2 of 4 additives");
    fireEvent.click(screen.getByRole("checkbox", { name: /Flagged/ }));
    expect(screen.getByText(/No additive matches/)).toBeTruthy();
  });
});

describe("guide parts", () => {
  test("category bars are as long as their count against the first", () => {
    const { container } = render(
      <CategoryBars
        categories={[
          { category_id: "sodas", name: "Sodas", products: 80 },
          { category_id: "candy", name: "Candy", products: 20 },
        ]}
      />,
    );
    const widths = Array.from(container.querySelectorAll<HTMLElement>("[data-bar]")).map(
      (bar) => bar.style.width,
    );
    expect(widths).toEqual(["100%", "25%"]);
    expect(screen.getByText("Sodas")).toBeTruthy();
  });

  test("example products link to their pages", () => {
    render(
      <ProductRows
        products={[
          {
            code: "0030000010402",
            name: "Oats",
            brand: null,
            category_main: null,
            nutriscore_grade: "a",
            nova_group: 1,
            image_url: null,
          },
        ]}
      />,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/product/0030000010402");
    expect(link.textContent).toContain("Brand not listed");
  });
});
