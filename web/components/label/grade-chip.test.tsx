import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { CHIP_CLASSES, GradeChip } from "./primitives";

afterEach(cleanup);

const css = readFileSync(join(__dirname, "../../app/globals.css"), "utf-8");

function token(name: string): string {
  const match = css.match(new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`token --color-${name} not found in globals.css`);
  return match[1];
}

/** WCAG 2.x relative luminance and contrast ratio. */
function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

describe("grade chip contrast (WCAG AA, 4.5:1)", () => {
  for (const grade of ["a", "b", "c", "d", "e"] as const) {
    test(`grade ${grade.toUpperCase()} text meets AA on its background`, () => {
      const text = CHIP_CLASSES[grade].includes("text-paper") ? token("paper") : token("ink");
      const ratio = contrast(text, token(`grade-${grade}`));
      expect(ratio, `ratio ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5);
    });
  }

  test("ratios recorded in DESIGN.md match the tokens", () => {
    const design = readFileSync(join(__dirname, "../../../docs/DESIGN.md"), "utf-8");
    const expected = {
      a: contrast(token("paper"), token("grade-a")),
      b: contrast(token("ink"), token("grade-b")),
      c: contrast(token("ink"), token("grade-c")),
      d: contrast(token("ink"), token("grade-d")),
      e: contrast(token("ink"), token("grade-e")),
    };
    const line = design.split("\n").find((l) => l.startsWith("- Text on grade chips:")) ?? "";
    expect(line).toContain(`white on A is ${expected.a.toFixed(1)}:1`);
    expect(line).toContain(`black on B ${expected.b.toFixed(1)}`);
    expect(line).toContain(`C ${expected.c.toFixed(1)}`);
    expect(line).toContain(`D ${expected.d.toFixed(1)}`);
    expect(line).toContain(`E ${expected.e.toFixed(1)}`);
  });
});

describe("GradeChip", () => {
  test("shows the letter and names the grade for screen readers", () => {
    render(<GradeChip grade="b" />);
    const chip = screen.getByRole("img", { name: "Nutri-Score B" });
    expect(chip.textContent).toBe("B");
    expect(chip.className).toContain("bg-grade-b");
  });

  test("says so when there is no grade, without colour", () => {
    const { container } = render(<GradeChip grade={null} />);
    expect(container.textContent).toBe("No Nutri-Score");
    expect(container.innerHTML).not.toContain("bg-grade");
  });
});
