import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { Header } from "./header";

afterEach(cleanup);

test("header links home and to the pages that exist", () => {
  render(<Header />);
  expect(screen.getByRole("link", { name: "LabelLens" }).getAttribute("href")).toBe("/");
  const nav = screen.getByRole("navigation", { name: "Main" });
  const links = Array.from(nav.querySelectorAll("a")).map((a) => [a.textContent, a.getAttribute("href")]);
  expect(links).toEqual([
    ["Read a label", "/label"],
    ["Dashboard", "/dashboard"],
    ["Graph", "/graph"],
    ["Ask", "/ask"],
    ["About", "/about"],
  ]);
});
