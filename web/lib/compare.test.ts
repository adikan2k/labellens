import { describe, expect, test } from "vitest";

import type { Additive, Nutrition } from "./api";
import { additiveGroups, compareHref, difference, nutritionGroups, parseCodes } from "./compare";
import { compareTitle } from "./metadata";

const nutrition = (over: Partial<Nutrition> = {}): Nutrition => ({
  energy_kcal_100g: 376,
  sugars_100g: 4.4,
  salt_100g: 1.2,
  fat_100g: 6.7,
  saturated_fat_100g: 1.2,
  fiber_100g: 10,
  proteins_100g: 12.4,
  ...over,
});

const additive = (id: string, e: string | null, name: string): Additive => ({
  additive_id: id,
  e_number: e,
  name,
  function: null,
  explainer: null,
});

describe("parseCodes", () => {
  test("digits only, no repeats, at most two", () => {
    expect(parseCodes("0016000275287,0016000169685")).toEqual(["0016000275287", "0016000169685"]);
    expect(parseCodes(" 1 , 1 ,2,3")).toEqual(["1", "2"]);
    expect(parseCodes("abc,12x,,42")).toEqual(["42"]);
    expect(parseCodes(["1", "2"])).toEqual(["1", "2"]);
    expect(parseCodes(undefined)).toEqual([]);
  });

  test("hrefs round-trip", () => {
    expect(parseCodes(compareHref(["1", "2"]).split("=")[1])).toEqual(["1", "2"]);
  });
});

describe("difference", () => {
  test("the second against the first, as a label prints it", () => {
    expect(difference("sugars_100g", 12, 6)).toBe("6 g less");
    expect(difference("sugars_100g", 2, 4.5)).toBe("2.5 g more");
    expect(difference("energy_kcal_100g", 376, 393)).toBe("17 kcal more");
  });

  test("the same as printed is the same", () => {
    expect(difference("sugars_100g", 4.42, 4.38)).toBe("Same");
    expect(difference("salt_100g", 0, 0)).toBe("Same");
  });

  test("unknown when either value is missing", () => {
    expect(difference("fiber_100g", null, 3)).toBeNull();
    expect(difference("fiber_100g", 3, null)).toBeNull();
  });
});

describe("nutritionGroups", () => {
  test("US label order, formatted, missing as null", () => {
    const groups = nutritionGroups(nutrition(), nutrition({ sugars_100g: null, fat_100g: 1 }));
    expect(groups.flat().map((r) => r.label)).toEqual([
      "Energy", "Fat", "Saturated fat", "Salt", "Fiber", "Sugars", "Protein",
    ]); // prettier-ignore
    const sugars = groups.flat().find((r) => r.key === "sugars_100g")!;
    expect([sugars.a, sugars.b, sugars.difference]).toEqual(["4.4 g", null, null]);
    const fat = groups.flat().find((r) => r.key === "fat_100g")!;
    expect([fat.a, fat.b, fat.difference]).toEqual(["6.7 g", "1 g", "5.7 g less"]);
    expect(groups.flat().find((r) => r.key === "saturated_fat_100g")!.indent).toBe(true);
  });
});

describe("additiveGroups", () => {
  test("in both, only in the first, only in the second", () => {
    const lecithin = additive("en:e322", "E322", "Lecithins");
    const citric = additive("en:e330", "E330", "Citric acid");
    const bht = additive("en:e321", "E321", "BHT");
    const groups = additiveGroups([lecithin, citric], [bht, lecithin]);
    expect(groups.both.map((x) => x.e_number)).toEqual(["E322"]);
    expect(groups.onlyA.map((x) => x.e_number)).toEqual(["E330"]);
    expect(groups.onlyB.map((x) => x.e_number)).toEqual(["E321"]);
  });
});

describe("compareTitle", () => {
  test("names both, or the one being compared", () => {
    expect(compareTitle([{ name: "Cheerios" }, { name: "Honey Nut Cheerios" }])).toBe(
      "Cheerios vs Honey Nut Cheerios",
    );
    expect(compareTitle([{ name: "Cheerios" }])).toBe("Compare Cheerios");
    expect(compareTitle([])).toBe("Compare products");
  });
});
