import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { Footer, ODBL_URL, OFF_URL } from "./footer";

afterEach(cleanup);

test("footer carries the ODbL attribution sentence", () => {
  render(<Footer />);

  const footer = screen.getByRole("contentinfo");
  expect(footer.textContent).toContain(
    "Contains data from Open Food Facts, available under the Open Database License",
  );
});

test("footer links to Open Food Facts and the licence", () => {
  render(<Footer />);

  expect(screen.getByRole("link", { name: "Open Food Facts" }).getAttribute("href")).toBe(OFF_URL);
  expect(screen.getByRole("link", { name: "Open Database License" }).getAttribute("href")).toBe(
    ODBL_URL,
  );
  expect(OFF_URL).toBe("https://world.openfoodfacts.org");
  expect(ODBL_URL).toBe("https://opendatacommons.org/licenses/odbl/1-0/");
});
