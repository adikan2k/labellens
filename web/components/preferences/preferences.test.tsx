import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

import type { AdditiveListItem, Nutrition } from "@/lib/api";
import { NO_PREFERENCES, readPreferences, writePreferences, type Checkable } from "@/lib/preferences";

import { AvoidButton } from "./avoid-button";
import { PreferencesForm } from "./preferences-form";
import { RulesCompareRow, YourRules } from "./your-rules";

const nutrition: Nutrition = {
  energy_kcal_100g: 400,
  fat_100g: 10,
  saturated_fat_100g: 5,
  sugars_100g: 30,
  salt_100g: 1,
  fiber_100g: null,
  proteins_100g: 8,
};
const product: Checkable = { nutrition, nutriscore_grade: "d", nova_group: 4, additives: [] };
const item = (id: string, e: string, name: string): AdditiveListItem => ({
  additive_id: id,
  slug: id.slice(3),
  e_number: e,
  name,
  function: null,
  flagged: false,
  product_count: 5,
});
const ADDITIVES = [item("en:e330", "E330", "Citric acid"), item("en:e129", "E129", "Allura red")];

beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("YourRules", () => {
  test("with no rules, a line invites setting some (or nothing, when asked)", () => {
    const { container, unmount } = render(<YourRules subject={product} />);
    expect(screen.getByRole("link").getAttribute("href")).toBe("/preferences");
    expect(container.querySelector("section")).toBeNull();
    unmount();
    const quiet = render(<YourRules subject={product} prompt={false} />);
    expect(quiet.container.textContent).toBe("");
  });

  test("each rule with its outcome in words, and what the product has unless it meets it", () => {
    writePreferences({ ...NO_PREFERENCES, limits: { sugars_100g: 10, salt_100g: 2 }, minGrade: "b" });
    render(<YourRules subject={{ ...product, nutriscore_grade: null }} />);
    const box = screen.getByRole("region", { name: "Your rules" });
    const rows = Array.from(box.querySelectorAll("li")).map((li) => [
      li.getAttribute("data-outcome"),
      li.textContent,
    ]);
    expect(rows).toEqual([
      ["misses", "Sugars: 10 g or less per 100 gMissesIt has 30 g."],
      ["meets", "Salt: 2 g or less per 100 gMeets"],
      ["unknown", "Nutri-Score B or betterNot knownIt has no Nutri-Score."],
    ]);
  });

  test("updates when the rules change elsewhere", () => {
    render(<YourRules subject={product} />);
    expect(screen.queryByRole("region", { name: "Your rules" })).toBeNull();
    act(() => {
      writePreferences({ ...NO_PREFERENCES, avoidUltraProcessed: true });
    });
    expect(screen.getByRole("region", { name: "Your rules" }).textContent).toContain("Misses");
  });
});

describe("RulesCompareRow", () => {
  const table = (node: ReactNode) => (
    <table>
      <tbody>{node}</tbody>
    </table>
  );

  test("nothing without rules; a verdict per product with them", () => {
    const { container, rerender } = render(table(<RulesCompareRow a={product} b={product} />));
    expect(container.querySelector("[data-row=rules]")).toBeNull();
    act(() => {
      writePreferences({ ...NO_PREFERENCES, limits: { sugars_100g: 40 }, avoidUltraProcessed: true });
    });
    rerender(table(<RulesCompareRow a={product} b={{ ...product, nova_group: 3 }} />));
    const cells = Array.from(container.querySelectorAll("[data-row=rules] td")).map(
      (td) => td.textContent,
    );
    expect(cells).toEqual(["Misses 1", "Meets all 2"]);
  });
});

describe("PreferencesForm", () => {
  test("starts empty, and each change is saved at once", () => {
    render(<PreferencesForm additives={ADDITIVES} />);
    expect(screen.getByRole("status").textContent).toBe("No rules set.");
    const sugars = screen.getByRole("spinbutton", { name: "Sugars" }) as HTMLInputElement;
    expect(sugars.value).toBe("");
    fireEvent.change(sugars, { target: { value: "12.5" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Nutri-Score" }), {
      target: { value: "c" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /ultra-processed/ }));
    expect(readPreferences()).toEqual({
      limits: { sugars_100g: 12.5 },
      minGrade: "c",
      avoidUltraProcessed: true,
      avoidAdditives: [],
    });
    expect(screen.getByRole("status").textContent).toBe("Saved in this browser.");
  });

  test("an out-of-range limit is not saved, and says why", () => {
    render(<PreferencesForm additives={ADDITIVES} />);
    fireEvent.change(screen.getByRole("spinbutton", { name: "Salt" }), { target: { value: "500" } });
    expect(screen.getByText(/from 0 to 100/)).toBeTruthy();
    expect(readPreferences().limits).toEqual({});
  });

  test("find an additive, avoid it, remove it", () => {
    render(<PreferencesForm additives={ADDITIVES} />);
    fireEvent.change(screen.getByRole("textbox", { name: /Find an additive/ }), {
      target: { value: "e129" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Avoid Allura red" }));
    expect(readPreferences().avoidAdditives).toEqual([
      { id: "en:e129", name: "Allura red", e_number: "E129" },
    ]);
    const avoided = screen.getByRole("list", { name: "Additives you avoid" });
    expect(avoided.querySelector("a")?.getAttribute("href")).toBe("/additives/e129");
    fireEvent.click(screen.getByRole("button", { name: "Remove Allura red" }));
    expect(readPreferences().avoidAdditives).toEqual([]);
  });

  test("clear removes every rule and empties the boxes", () => {
    writePreferences({ ...NO_PREFERENCES, limits: { salt_100g: 1 } });
    render(<PreferencesForm additives={null} />);
    const salt = () => screen.getByRole("spinbutton", { name: "Salt" }) as HTMLInputElement;
    expect(salt().value).toBe("1");
    expect(screen.getByText(/additive list is not available/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear my rules" }));
    expect(readPreferences()).toEqual(NO_PREFERENCES);
    expect(salt().value).toBe("");
  });
});

test("AvoidButton adds the additive, then links to the rules", () => {
  render(<AvoidButton additive={{ id: "en:e129", name: "Allura red", e_number: "E129" }} />);
  fireEvent.click(screen.getByRole("button", { name: "Add to the additives I avoid" }));
  expect(readPreferences().avoidAdditives).toHaveLength(1);
  expect(screen.getByRole("link").getAttribute("href")).toBe("/preferences");
});
