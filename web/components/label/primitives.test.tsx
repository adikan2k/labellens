import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { DataRow, Panel, Rule } from "./primitives";

afterEach(cleanup);

test("Rule uses the token class and is hidden from assistive tech", () => {
  const { container } = render(<Rule weight="heavy" />);
  const rule = container.firstElementChild as HTMLElement;
  expect(rule.className).toContain("rule-heavy");
  expect(rule.getAttribute("aria-hidden")).toBe("true");
});

test("DataRow shows label and value", () => {
  render(<DataRow label="Sugars" value="12 g" />);
  expect(screen.getByText("Sugars")).toBeTruthy();
  expect(screen.getByText("12 g").className).toContain("type-data-value");
});

test("DataRow never shows a blank cell for a missing value", () => {
  const { container } = render(<DataRow label="Fiber" missing />);
  expect(container.textContent).toContain("Not listed");
});

test("Panel is a section with the panel border", () => {
  render(
    <Panel aria-labelledby="t">
      <h2 id="t">Nutrition Facts</h2>
    </Panel>,
  );
  const panel = screen.getByRole("region", { name: "Nutrition Facts" });
  expect(panel.className).toContain("panel");
});
