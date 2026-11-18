import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, type Product } from "@/lib/api";
import { RateLimited } from "@/lib/ask";
import { LABEL } from "@/lib/copy";
import type { LabelResponse } from "@/lib/label";

const readLabel = vi.fn();
vi.mock("@/lib/label", async (original) => ({
  ...(await original<typeof import("@/lib/label")>()),
  readLabel: (...args: unknown[]) => readLabel(...args),
  downscale: async (file: File) => file,
}));

const { fitWithin, labelAsProduct, LABEL_SAMPLES, MAX_EDGE, PHOTO_CODE } = await import("@/lib/label");
const { LabelResult } = await import("./label-result");
const { ReadLabelPanel } = await import("./read-label-panel");

const source = {
  name: "Open Food Facts",
  url: "https://world.openfoodfacts.org",
  licence: "ODbL-1.0",
  licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
  snapshot_date: "2026-11-17",
} as const;

const nutrition = {
  energy_kcal_100g: 400,
  sugars_100g: 20,
  salt_100g: 1.67,
  fat_100g: 10,
  saturated_fat_100g: 2,
  fiber_100g: null,
  proteins_100g: 8,
};

const product: Product = {
  code: "0016000275287",
  name: "Oat Squares",
  brand: "Zorblax",
  category_main: "breakfast-cereals",
  nutriscore_grade: "c",
  nova_group: 4,
  image_url: null,
  category_name: "Breakfast cereals and oats",
  category_source: "off_tags",
  completeness: 0.9,
  nutrition: { ...nutrition, sugars_100g: 12, fiber_100g: 6 },
  additives: [],
  ingredients: [],
  off_url: "https://world.openfoodfacts.org/product/0016000275287",
  in_graph: false,
};

function response(over: Partial<LabelResponse> = {}): LabelResponse {
  return {
    is_food_label: true,
    label: {
      name: "Oat Squares",
      brand: "Zorblax",
      barcode: null,
      category_id: "breakfast-cereals",
      category_name: "Breakfast cereals and oats",
      basis: "per_serving",
      serving_size_g: 30,
      conversion_note: "Converted from per serving (30 g or ml) to per 100 g or ml.",
      nutrition,
      ingredients: [
        { ingredient_id: "en:oat", name: "Oats", rank: 1, explainer: { text: "Rolled oats.", ai_generated: true } },
        { ingredient_id: "label:2", name: "Sugar", rank: 2, explainer: null },
      ],
      additives: [
        { additive_id: "en:e330", e_number: "E330", name: "Citric acid", function: null, explainer: null, flagged: false },
        { additive_id: "en:e250", e_number: "E250", name: "Sodium nitrite", function: null, explainer: null, flagged: true },
      ],
      unmatched_additives: ["zorblaxate"],
    },
    match: { how: "name", product },
    suggestions: [
      {
        product: { ...product, code: "0000000000024", name: "Plain Oats", nutriscore_grade: "a" },
        reason: "Nutri-Score A instead of C · no additives instead of 2 · none flagged by Open Food Facts",
        additive_count: 0,
      },
    ],
    suggestions_kind: "swaps",
    source,
    ...over,
  };
}

afterEach(cleanup);

describe("label helpers", () => {
  test("photos are scaled to fit the model's long edge, never enlarged", () => {
    expect(fitWithin(4032, 3024)).toEqual({ width: MAX_EDGE, height: 1176 });
    expect(fitWithin(3024, 4032)).toEqual({ width: 1176, height: MAX_EDGE });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });

  test("a label stands in as a product for the comparison", () => {
    const stand = labelAsProduct(response().label!);
    expect(stand.code).toBe(PHOTO_CODE);
    expect(stand.name).toBe("Oat Squares (your photo)");
    expect(stand.nutrition).toBe(nutrition);
    expect(labelAsProduct({ ...response().label!, name: null }).name).toBe("Your photo");
  });

  test("every sample has its photos and its recorded read", () => {
    const dir = join(__dirname, "..", "..", "public");
    expect(LABEL_SAMPLES.length).toBe(3);
    for (const sample of LABEL_SAMPLES) {
      for (const photo of sample.photos) expect(existsSync(join(dir, photo)), photo).toBe(true);
      const recorded = JSON.parse(
        readFileSync(join(dir, "label-samples", `${sample.slug}.json`), "utf-8"),
      ) as LabelResponse;
      expect(recorded.is_food_label, sample.slug).toBe(true);
      expect(recorded.source.name).toBe("Open Food Facts");
    }
  });
});

describe("LabelResult", () => {
  test("shows what was read, as read by AI, per 100 g with the conversion note", () => {
    render(<LabelResult result={response()} />);
    const article = screen.getByRole("article", { name: "What the label says" });
    expect(within(article).getByRole("heading", { level: 2, name: "Oat Squares" })).toBeTruthy();
    expect(within(article).getByText(LABEL.readByAi)).toBeTruthy();
    expect(within(article).getByText(/Converted from per serving \(30 g or ml\)/)).toBeTruthy();
    const panel = within(article).getByRole("region", { name: "Nutrition Facts" });
    expect(within(panel).getByText("400 kcal")).toBeTruthy();
    expect(within(panel).getByText("Not listed")).toBeTruthy(); // fiber was not printed
  });

  test("a flagged additive says so in words, and unknown ones are listed", () => {
    render(<LabelResult result={response()} />);
    const section = screen.getByRole("region", { name: "Additives (2)" });
    expect(within(section).getAllByText("Flagged by Open Food Facts")).toHaveLength(1);
    expect(within(section).getByText(LABEL.unmatchedAdditives(["zorblaxate"]))).toBeTruthy();
  });

  test("a match is 'looks like', linked and compared, never asserted", () => {
    render(<LabelResult result={response()} />);
    const section = screen.getByRole("region", { name: LABEL.looksLike });
    const link = within(section).getAllByRole("link", { name: "Oat Squares" })[0];
    expect(link.getAttribute("href")).toBe("/product/0016000275287");
    expect(within(section).getByText(/by its name and brand/)).toBeTruthy();
    const table = within(section).getByRole("table");
    const heads = within(table).getAllByRole("columnheader");
    expect(heads[0].textContent).toContain("Oat Squares (your photo)");
    expect(within(heads[0]).queryByRole("link")).toBeNull(); // the photo has no product page
    expect(within(table).getByText("8 g less")).toBeTruthy(); // sugars: 12 against 20
  });

  test("swaps compare with the matched product", () => {
    render(<LabelResult result={response()} />);
    const section = screen.getByRole("region", { name: LABEL.swapsHeading });
    const compare = within(section).getByRole("link", { name: "Compare with Plain Oats" });
    expect(compare.getAttribute("href")).toBe("/compare?codes=0016000275287,0000000000024");
  });

  test("with no match, well-graded products are offered as that and nothing more", () => {
    const result = response({ match: null, suggestions_kind: "category" });
    render(<LabelResult result={result} />);
    expect(screen.getByRole("region", { name: LABEL.noMatch })).toBeTruthy();
    const section = screen.getByRole("region", {
      name: "Well-graded products in breakfast cereals and oats",
    });
    expect(within(section).getByText(LABEL.categoryNote)).toBeTruthy();
    expect(within(section).queryByRole("link", { name: /^Compare/ })).toBeNull();
  });

  test("a barcode read from the pack but missing from the data links to adding it", () => {
    const label = { ...response().label!, barcode: "0123456789012" };
    render(<LabelResult result={response({ label, match: null, suggestions: [], suggestions_kind: null })} />);
    const section = screen.getByRole("region", { name: LABEL.noMatch });
    expect(within(section).getByRole("link").getAttribute("href")).toContain("code=0123456789012");
  });

  test("a photo that is not a label says so", () => {
    render(<LabelResult result={response({ is_food_label: false, label: null, match: null, suggestions: [] })} />);
    expect(screen.getByText(LABEL.notALabel)).toBeTruthy();
    expect(screen.queryByRole("article")).toBeNull();
  });
});

describe("ReadLabelPanel", () => {
  const photo = (name: string) => new File(["x"], name, { type: "image/jpeg" });

  beforeEach(() => {
    readLabel.mockReset();
    URL.createObjectURL = vi.fn(() => "blob:label-photo");
    URL.revokeObjectURL = vi.fn();
  });

  function addPhotos(...names: string[]) {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: names.map(photo) } });
  }

  test("nothing can be read until a photo is added; the input opens the camera on a phone", () => {
    render(<ReadLabelPanel />);
    expect((screen.getByRole("button", { name: LABEL.read }) as HTMLButtonElement).disabled).toBe(true);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.accept).toBe("image/*");
    expect(input.getAttribute("capture")).toBe("environment");
    expect(screen.getByText(LABEL.privacy)).toBeTruthy();
  });

  test("photos show as tiles, can be removed, and are read on request", async () => {
    readLabel.mockResolvedValue(response());
    render(<ReadLabelPanel />);
    addPhotos("ingredients.jpg", "nutrition.jpg");
    const tiles = screen.getByRole("list", { name: "Photos to read" });
    expect(within(tiles).getAllByRole("img")).toHaveLength(2);
    expect(screen.queryByRole("button", { name: LABEL.addAnother })).toBeNull(); // two is the most
    fireEvent.click(within(tiles).getAllByRole("button", { name: /Remove/ })[1]);
    expect(within(tiles).getAllByRole("img")).toHaveLength(1);
    expect(URL.revokeObjectURL).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: LABEL.read }));
    expect(screen.getByText(LABEL.reading)).toBeTruthy();
    await screen.findByRole("article", { name: "What the label says" });
    expect(readLabel.mock.calls[0][0]).toHaveLength(1);
  });

  test("a third photo is turned away with a reason", () => {
    render(<ReadLabelPanel />);
    addPhotos("a.jpg", "b.jpg", "c.jpg");
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("alert").textContent).toBe(LABEL.tooMany);
  });

  test("the hourly limit, the spent cap and an unconfigured reader each read plainly", async () => {
    render(<ReadLabelPanel />);
    addPhotos("a.jpg");
    readLabel.mockRejectedValueOnce(new RateLimited("That's 10 labels this hour from here.", 600));
    fireEvent.click(screen.getByRole("button", { name: LABEL.read }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe(
        "That's 10 labels this hour from here. Try again in about 10 minutes.",
      ),
    );
    readLabel.mockRejectedValueOnce(new ApiError(503, "Today's budget for reading labels is used up."));
    fireEvent.click(screen.getByRole("button", { name: LABEL.read }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/budget/));
    readLabel.mockRejectedValueOnce(new ApiError(503, "The label reader is not configured."));
    fireEvent.click(screen.getByRole("button", { name: LABEL.read }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe(LABEL.unavailable));
  });

  test("a sample shows its recorded read without calling the API", async () => {
    const fetched = vi.fn(async () => new Response(JSON.stringify(response()), { status: 200 }));
    vi.stubGlobal("fetch", fetched);
    render(<ReadLabelPanel />);
    fireEvent.click(screen.getByRole("button", { name: LABEL_SAMPLES[0].title }));
    await screen.findByRole("article", { name: "What the label says" });
    expect(fetched).toHaveBeenCalledWith(`/label-samples/${LABEL_SAMPLES[0].slug}.json`);
    expect(readLabel).not.toHaveBeenCalled();
    expect(screen.getByText(LABEL.sampleNote)).toBeTruthy();
    expect(screen.getByText(LABEL.sampleCredit)).toBeTruthy();
    vi.unstubAllGlobals();
  });
});
