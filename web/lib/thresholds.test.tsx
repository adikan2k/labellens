import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { NutrientFlags } from "@/components/product/nutrient-flags";

import type { Nutrition } from "./api";
import { flagFor, isDrink, level, nutrientFlags, THRESHOLDS } from "./thresholds";

afterEach(cleanup);

const nutrition = (over: Partial<Nutrition> = {}): Nutrition => ({
  energy_kcal_100g: 400,
  sugars_100g: 10,
  salt_100g: 1,
  fat_100g: 10,
  saturated_fat_100g: 3,
  fiber_100g: 2,
  proteins_100g: 5,
  ...over,
});

describe("the UK front-of-pack thresholds", () => {
  test("are the published figures, per 100 g and per 100 ml", () => {
    expect(THRESHOLDS.food).toEqual({
      fat_100g: { low: 3, high: 17.5 },
      saturated_fat_100g: { low: 1.5, high: 5 },
      sugars_100g: { low: 5, high: 22.5 },
      salt_100g: { low: 0.3, high: 1.5 },
    });
    expect(THRESHOLDS.drink).toEqual({
      fat_100g: { low: 1.5, high: 8.75 },
      saturated_fat_100g: { low: 0.75, high: 2.5 },
      sugars_100g: { low: 2.5, high: 11.25 },
      salt_100g: { low: 0.3, high: 0.75 },
    });
  });

  test("low is at or under the low figure; high is over the high one", () => {
    const sugars = THRESHOLDS.food.sugars_100g;
    expect(level(5, sugars)).toBe("low");
    expect(level(5.01, sugars)).toBe("medium");
    expect(level(22.5, sugars)).toBe("medium");
    expect(level(22.51, sugars)).toBe("high");
    expect(level(0, sugars)).toBe("low");
    expect(level(null, sugars)).toBeNull();
  });

  test("drinks are judged per 100 ml by their own thresholds", () => {
    expect(isDrink("sodas") && isDrink("juices") && isDrink("milk")).toBe(true);
    expect(isDrink("breakfast-cereals") || isDrink(null)).toBe(false);
    // 10.6 g sugars: medium for a food, but high is 11.25 for a drink, so medium there too.
    expect(flagFor("sugars_100g", 10.6, "sodas")).toBeNull();
    expect(flagFor("sugars_100g", 12, "sodas")).toBe("high");
    expect(flagFor("sugars_100g", 12, "breakfast-cereals")).toBeNull();
    expect(flagFor("fiber_100g", 12, "breakfast-cereals")).toBeNull(); // fiber is not flagged
  });

  test("flags list high first, each in label order, and skip what is not listed", () => {
    const flags = nutrientFlags(
      nutrition({ fat_100g: 2, salt_100g: 2, sugars_100g: 30, saturated_fat_100g: null }),
      "breakfast-cereals",
    );
    expect(flags.map((f) => `${f.level} ${f.name}`)).toEqual([
      "high sugars",
      "high salt",
      "low fat",
    ]);
  });
});

describe("NutrientFlags", () => {
  test("high lines, then low ones, in words, with the source", () => {
    render(
      <NutrientFlags
        nutrition={nutrition({ sugars_100g: 33, salt_100g: 0.1, fat_100g: 2 })}
        categoryId="breakfast-cereals"
      />,
    );
    const section = screen.getByRole("region", { name: "High in, low in" });
    expect(within(section).getByRole("listitem").textContent).toBe("High in sugars");
    expect(within(section).getByText("Low in fat · Low in salt")).toBeTruthy();
    expect(within(section).getByRole("link", { name: "the UK front-of-pack criteria" })).toBeTruthy();
    expect(section.textContent).toContain("per 100 g");
    expect(section.innerHTML).not.toMatch(/grade-|text-\w+-\d/); // no colour
  });

  test("says when a product is judged as a drink", () => {
    render(<NutrientFlags nutrition={nutrition({ sugars_100g: 10.6, fat_100g: 0 })} categoryId="sodas" />);
    expect(screen.getByText(/per 100 ml, as a drink/)).toBeTruthy();
  });

  test("shows nothing when nothing is high or low", () => {
    const { container } = render(<NutrientFlags nutrition={nutrition()} categoryId="breakfast-cereals" />);
    expect(container.innerHTML).toBe("");
  });
});
