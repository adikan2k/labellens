import { existsSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { BarcodeMark, Header, NAV_LINKS } from "@/components/header";
import type { Product, StatsOverview } from "@/lib/api";
import { ean13CheckDigit, ean13Modules } from "@/lib/barcode";
import { HOME_WAYS_IN, MEASURED, SHELF, SPECIMEN } from "@/lib/copy";

import { Barcode } from "./barcode";
import { GradeStrip, gradeShares, Measured, tickerFacts, WaysIn } from "./bands";
import { Specimen } from "./specimen";
import { Ticker } from "./ticker";

afterEach(cleanup);

const stats = {
  product_count: 1000,
  named_product_count: 985260,
  brand_count: 10,
  category_count: 26,
  additive_count: 514,
  nutriscore: [
    { key: "a", label: "Nutri-Score A", count: 90 },
    { key: "b", label: "Nutri-Score B", count: 170 },
    { key: "c", label: "Nutri-Score C", count: 220 },
    { key: "d", label: "Nutri-Score D", count: 270 },
    { key: "e", label: "Nutri-Score E", count: 250 },
    { key: null, label: "No Nutri-Score", count: 600 },
  ],
  nova: [
    { key: "4", label: "Ultra-processed foods", count: 70 },
    { key: "1", label: "Unprocessed", count: 30 },
  ],
  categories: [{ key: "salty-snacks", label: "Chips, crackers and salty snacks", count: 70 }],
  category_sources: [],
  top_additives: [{ key: "en:e330", label: "E330 Citric acid", count: 101709 }],
  nutriscore_by_category: [],
  median_sugars_by_category: [],
  source: {
    name: "Open Food Facts",
    url: "https://world.openfoodfacts.org",
    licence: "ODbL-1.0",
    licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
    snapshot_date: "2026-11-17",
  },
} satisfies StatsOverview;

describe("the barcode", () => {
  // From the encoder whose bars the real reader decoded end to end (scanner test, PR #24).
  const CHEERIOS =
    "10100011010011001010111100011010001101000110101010110110010001001001110110110010010001000100101";
  const PEN =
    "10100011010100111010111101111010001001011001101010100001010000101000010111010010000101100110101";

  test("draws the EAN-13 bars a scanner reads", () => {
    expect(ean13Modules("0016000275287")).toBe(CHEERIOS);
    expect(ean13Modules("4006381333931")).toBe(PEN);
    expect(ean13Modules("016000275287")).toBe(CHEERIOS); // UPC-A is EAN-13 with a leading 0
  });

  test("draws nothing for a code that isn't a valid EAN-13", () => {
    expect(ean13CheckDigit("001600027528")).toBe(7);
    expect(ean13Modules("0016000275288")).toBeNull(); // wrong check digit
    expect(ean13Modules("12345")).toBeNull();
    const { container } = render(<Barcode code="0016000275288" />);
    expect(container.innerHTML).toBe("");
  });

  test("renders as an image named by its digits, with the digits under it", () => {
    render(<Barcode code="0016000275287" />);
    const svg = screen.getByRole("img", { name: "Barcode 0016000275287" });
    const modules = [...svg.querySelectorAll("rect")].reduce(
      (n, r) => n + Number(r.getAttribute("width")),
      0,
    );
    expect(modules).toBe(CHEERIOS.replace(/0/g, "").length); // every bar module drawn
    expect(screen.getByText("0016000275287")).toBeTruthy();
  });
});

describe("the specimen", () => {
  const product = (code: string, name: string, grade: "a" | "c" | "e"): Product => ({
    code,
    name,
    brand: "Brand",
    category_main: null,
    nutriscore_grade: grade,
    nova_group: null,
    image_url: null,
    category_name: null,
    category_source: null,
    completeness: null,
    nutrition: {
      energy_kcal_100g: 379,
      sugars_100g: 1,
      salt_100g: 0,
      fat_100g: 6.9,
      saturated_fat_100g: 1.2,
      fiber_100g: 10,
      proteins_100g: 13,
    },
    additives: [],
    ingredients: [],
    off_url: "",
    in_graph: false,
  });

  test("shows a real label and barcode, and cycles to the next product", () => {
    render(
      <Specimen
        products={[
          product("0030000010402", "Old Fashioned Oats", "a"),
          product("0016000275287", "Cheerios", "c"),
        ]}
      />,
    );
    const section = screen.getByRole("region", { name: SPECIMEN.label });
    expect(within(section).getByRole("link", { name: "Old Fashioned Oats" }).getAttribute("href")).toBe(
      "/product/0030000010402",
    );
    expect(within(section).getByRole("img", { name: "Nutri-Score A" })).toBeTruthy();
    expect(within(section).getByRole("region", { name: "Nutrition Facts" })).toBeTruthy();
    expect(within(section).getByRole("img", { name: "Barcode 0030000010402" })).toBeTruthy();
    fireEvent.click(within(section).getByRole("button", { name: SPECIMEN.next }));
    expect(within(section).getByRole("link", { name: "Cheerios" })).toBeTruthy();
  });

  test("with the API asleep there is no specimen", () => {
    const { container } = render(<Specimen products={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("the bands", () => {
  test("the ticker says the dashboard's findings once to screen readers, and can be paused", () => {
    const facts = tickerFacts(stats);
    expect(facts[0]).toBe("985,260 US products");
    expect(facts).toContain("E330 Citric acid is in more products than any other additive: 101,709");
    render(<Ticker facts={facts} />);
    const band = screen.getByRole("region", { name: SHELF.tickerLabel });
    const lists = band.querySelectorAll("ul");
    expect(lists).toHaveLength(2);
    expect(lists[1].getAttribute("aria-hidden")).toBe("true");
    const pause = within(band).getByRole("button", { name: SHELF.pause });
    fireEvent.click(pause);
    expect(pause.getAttribute("aria-pressed")).toBe("true");
    expect(band.querySelector("[data-paused]")).not.toBeNull();
  });

  test("the strip sizes each grade by its share of graded products", () => {
    const shares = gradeShares(stats);
    expect(shares.map((s) => s.grade)).toEqual(["a", "b", "c", "d", "e"]);
    expect(shares.map((s) => Math.round(s.share * 100))).toEqual([9, 17, 22, 27, 25]);
    render(<GradeStrip stats={stats} />);
    const [wide] = screen.getAllByRole("list", { name: SHELF.listLabel });
    const blocks = [...wide.querySelectorAll("li")];
    expect(blocks.map((b) => (b as HTMLElement).style.flexGrow)).toEqual(["90", "170", "220", "270", "250"]);
    expect(blocks[0].className).toContain("bg-grade-a");
    expect(within(wide).getByText("9%")).toBeTruthy();
    expect(screen.getByRole("link", { name: SHELF.link }).getAttribute("href")).toBe("/dashboard#nutriscore");
  });

  test("tiles for the first three ways in, links for the rest", () => {
    render(<WaysIn />);
    const tiles = screen.getAllByRole("listitem").map((li) => li.querySelector("a")?.getAttribute("href"));
    expect(tiles).toEqual(HOME_WAYS_IN.slice(0, 3).map((w) => w.href));
    expect(screen.getByRole("link", { name: "The dashboard" }).getAttribute("href")).toBe("/dashboard");
  });

  test("every measured number links to an eval report that exists", () => {
    render(<Measured />);
    for (const m of MEASURED) {
      expect(existsSync(join(__dirname, "..", "..", "..", m.file)), m.file).toBe(true);
      expect(screen.getByText(m.value)).toBeTruthy();
    }
  });
});

test("the header leads with Read a label and has the barcode mark", () => {
  const { container } = render(<Header />);
  expect(NAV_LINKS[0]).toEqual({ href: "/label", label: "Read a label" });
  expect(screen.getByRole("link", { name: "LabelLens" }).querySelector("svg")).not.toBeNull();
  const { container: mark } = render(<BarcodeMark />);
  expect(mark.querySelectorAll("rect")).toHaveLength(7);
  expect(container.querySelector("nav")).not.toBeNull();
});
