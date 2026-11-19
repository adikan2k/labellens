import { beforeEach, describe, expect, test } from "vitest";

import type { Nutrition } from "./api";
import {
  checkRules,
  cleanPreferences,
  clearPreferences,
  grams,
  hasRules,
  meetsAll,
  NO_PREFERENCES,
  PREFERENCES_KEY,
  readPreferences,
  verdict,
  writePreferences,
  type Checkable,
  type Preferences,
} from "./preferences";

const nutrition: Nutrition = {
  energy_kcal_100g: 400,
  fat_100g: 10,
  saturated_fat_100g: 5,
  sugars_100g: 12.5,
  salt_100g: 1,
  fiber_100g: null,
  proteins_100g: 8,
};
const product: Checkable = {
  nutrition,
  nutriscore_grade: "c",
  nova_group: 4,
  additives: [{ additive_id: "en:e129", name: "Allura red", e_number: "E129" }],
};
const rules = (p: Partial<Preferences>): Preferences => ({ ...NO_PREFERENCES, ...p });

beforeEach(() => localStorage.clear());

describe("checkRules", () => {
  test("no rules, no checks", () => {
    expect(checkRules(NO_PREFERENCES, product)).toEqual([]);
    expect(hasRules(NO_PREFERENCES)).toBe(false);
  });

  test("a limit is met at exactly the limit and missed just above it", () => {
    const at = checkRules(rules({ limits: { sugars_100g: 12.5 } }), product)[0];
    expect(at).toMatchObject({ outcome: "meets", rule: "Sugars: 12.5 g or less per 100 g" });
    const below = checkRules(rules({ limits: { sugars_100g: 12.4 } }), product)[0];
    expect(below).toMatchObject({ outcome: "misses", detail: "It has 12.5 g." });
  });

  test("a missing value is not known, never a pass", () => {
    const check = checkRules(rules({ limits: { salt_100g: 1 } }), {
      ...product,
      nutrition: { ...nutrition, salt_100g: null },
    })[0];
    expect(check.outcome).toBe("unknown");
  });

  test("Nutri-Score: the chosen grade or better", () => {
    const at = (minGrade: Preferences["minGrade"], grade: Checkable["nutriscore_grade"]) =>
      checkRules(rules({ minGrade }), { ...product, nutriscore_grade: grade })[0].outcome;
    expect(at("c", "a")).toBe("meets");
    expect(at("c", "c")).toBe("meets");
    expect(at("b", "c")).toBe("misses");
    expect(at("b", null)).toBe("unknown");
    expect(checkRules(rules({ minGrade: "a" }), product)[0].rule).toBe("Nutri-Score A");
  });

  test("ultra-processed is NOVA 4; no group is not known", () => {
    const at = (nova: Checkable["nova_group"]) =>
      checkRules(rules({ avoidUltraProcessed: true }), { ...product, nova_group: nova })[0].outcome;
    expect([at(4), at(3), at(null)]).toEqual(["misses", "meets", "unknown"]);
  });

  test("avoided additives name the ones the product lists", () => {
    const avoid = [
      { id: "en:e129", name: "Allura red", e_number: "E129" },
      { id: "en:e102", name: "Tartrazine", e_number: "E102" },
    ];
    const check = checkRules(rules({ avoidAdditives: avoid }), product)[0];
    expect(check).toMatchObject({
      outcome: "misses",
      rule: "Without the 2 additives you avoid",
      detail: "It lists E129 Allura red.",
    });
    const one = checkRules(rules({ avoidAdditives: [avoid[1]] }), product)[0];
    expect(one).toMatchObject({ outcome: "meets", rule: "Without E102 Tartrazine" });
  });

  test("checks follow the form's order, and the verdict counts them", () => {
    const all = rules({
      limits: { saturated_fat_100g: 6, sugars_100g: 20 },
      minGrade: "d",
      avoidUltraProcessed: true,
    });
    const checks = checkRules(all, product);
    expect(checks.map((c) => c.key)).toEqual(["sugars_100g", "saturated_fat_100g", "grade", "nova"]);
    expect(verdict(checks)).toBe("Misses 1");
    expect(meetsAll(checks)).toBe(false);
    const met = checkRules(rules({ limits: { sugars_100g: 20 } }), product);
    expect([verdict(met), meetsAll(met)]).toEqual(["Meets it", true]);
    const unknown = checkRules(rules({ limits: { sugars_100g: 20 }, minGrade: "b" }), {
      ...product,
      nutriscore_grade: null,
    });
    expect(verdict(unknown)).toBe("Meets 1, 1 not known");
    expect(meetsAll(unknown)).toBe(false);
  });

  test("grams keep one decimal so near misses show", () => {
    expect([grams(10.44), grams(0), grams(0.01), grams(22.5)]).toEqual([
      "10.4 g",
      "0 g",
      "<0.1 g",
      "22.5 g",
    ]);
  });
});

describe("storage", () => {
  test("round trip, and clearing removes the key", () => {
    writePreferences(rules({ limits: { salt_100g: 0.3 }, minGrade: "b" }));
    expect(readPreferences()).toEqual(rules({ limits: { salt_100g: 0.3 }, minGrade: "b" }));
    clearPreferences();
    expect(localStorage.getItem(PREFERENCES_KEY)).toBeNull();
    expect(readPreferences()).toEqual(NO_PREFERENCES);
  });

  test("anything malformed is dropped", () => {
    localStorage.setItem(PREFERENCES_KEY, "{broken");
    expect(readPreferences()).toEqual(NO_PREFERENCES);
    const clean = cleanPreferences({
      limits: { sugars_100g: -1, salt_100g: "1", saturated_fat_100g: 4, fat_100g: 2 },
      minGrade: "z",
      avoidUltraProcessed: "yes",
      avoidAdditives: [
        { id: "en:e129", name: "Allura red", e_number: "E129" },
        { id: "en:e129", name: "again", e_number: null },
        { id: "", name: "nameless" },
        "en:e102",
      ],
    });
    expect(clean).toEqual({
      limits: { saturated_fat_100g: 4 },
      minGrade: null,
      avoidUltraProcessed: false,
      avoidAdditives: [{ id: "en:e129", name: "Allura red", e_number: "E129" }],
    });
  });
});
