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
    ["Additives", "/additives"],
    ["Dashboard", "/dashboard"],
    ["Graph", "/graph"],
    ["Ask", "/ask"],
    ["About", "/about"],
  ]);
});

test("on a phone the header keeps four links; the footer has the rest", () => {
  render(<Header />);
  const nav = screen.getByRole("navigation", { name: "Main" });
  const phoneOnly = Array.from(nav.querySelectorAll("li"))
    .filter((li) => !li.className.split(" ").includes("hidden"))
    .map((li) => li.textContent);
  expect(phoneOnly).toEqual(["Read a label", "Additives", "Dashboard", "Ask"]);
  expect(nav.querySelector("li.hidden")?.className).toBe("hidden md:list-item");
});
