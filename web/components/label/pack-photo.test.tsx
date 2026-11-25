import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { PackPhoto, thumbnail } from "./pack-photo";

afterEach(cleanup);

const SRC = "https://images.openfoodfacts.org/images/products/001/600/027/5263/front_en.400.jpg";
const OFF = "https://world.openfoodfacts.org/product/0016000275263";

test("the hero photo names the pack and credits Open Food Facts", () => {
  render(<PackPhoto src={SRC} name="Cheerios" size="hero" offUrl={OFF} />);
  const img = screen.getByRole("img", { name: "The pack of Cheerios" });
  expect(img.getAttribute("src")).toBe(SRC);
  expect(img.className).toContain("object-contain"); // never cropped
  expect(screen.getByText(/Photo: Open Food Facts contributors, CC BY-SA/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "See it on Open Food Facts" }).getAttribute("href")).toBe(OFF);
});

test("without a photo the hero is left out", () => {
  const { container } = render(<PackPhoto src={null} name="Cheerios" size="hero" offUrl={OFF} />);
  expect(container.innerHTML).toBe("");
});

test("a row thumbnail is decoration beside the name, loaded lazily", () => {
  const { container } = render(<PackPhoto src={SRC} name="Cheerios" size="row" />);
  const img = container.querySelector("img")!;
  expect(img.getAttribute("alt")).toBe("");
  expect(img.getAttribute("loading")).toBe("lazy");
  expect(container.firstElementChild?.className).toContain("h-12 w-12");
  // The 100 px photo, not the 400 px one the page's main photo uses.
  expect(img.getAttribute("src")).toBe(SRC.replace(".400.jpg", ".100.jpg"));
});

test("only Open Food Facts' 400 px photos are swapped for their 100 px version", () => {
  expect(thumbnail("https://images.openfoodfacts.org/x/front_en.8.400.jpg")).toBe(
    "https://images.openfoodfacts.org/x/front_en.8.100.jpg",
  );
  expect(thumbnail("https://images.openfoodfacts.org/x/front_en.8.full.jpg")).toBe(
    "https://images.openfoodfacts.org/x/front_en.8.full.jpg",
  );
});

test("a row without a photo keeps an empty frame, so rows line up", () => {
  const { container } = render(<PackPhoto src={null} name="Cheerios" size="row" />);
  expect(container.querySelector("img")).toBeNull();
  expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  expect(container.firstElementChild?.className).toContain("h-12 w-12");
});

test("a comparison column gets a larger thumbnail", () => {
  const { container } = render(<PackPhoto src={SRC} name="Cheerios" size="head" />);
  expect(container.firstElementChild?.className).toContain("h-24 w-24");
});
