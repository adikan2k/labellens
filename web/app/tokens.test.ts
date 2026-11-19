/**
 * Tailwind's default spacing scale is cleared in globals.css, so a spacing class whose step is
 * not one of DESIGN.md's tokens generates no CSS at all and fails silently (About's section
 * headings once sat flush against the paragraph above because of a `pt-10`). This test reads
 * the token steps from globals.css and checks every spacing class in the source uses one.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

import { describe, expect, test } from "vitest";

const WEB = join(__dirname, "..");
const SOURCE_DIRS = ["app", "components", "lib"];

const SPACING_PREFIXES = [
  "p", "px", "py", "pt", "pb", "pl", "pr", "ps", "pe",
  "m", "mx", "my", "mt", "mb", "ml", "mr", "ms", "me",
  "gap", "gap-x", "gap-y", "space-x", "space-y",
  "inset", "inset-x", "inset-y", "top", "bottom", "left", "right",
  "scroll-mt", "scroll-mb", "indent",
];

function tokenSteps(): Set<string> {
  const css = readFileSync(join(WEB, "app", "globals.css"), "utf-8");
  return new Set([...css.matchAll(/--spacing-([\d.]+):/g)].map((m) => m[1]));
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

// A spacing class with a numeric step, alone or after variants (`lg:pt-8`) or a minus sign.
const CLASS = new RegExp(
  String.raw`(?<![\w-])-?(${SPACING_PREFIXES.join("|")})-(\d+(?:\.\d+)?)(?![\w.])`,
  "g",
);

describe("design tokens", () => {
  test("globals.css defines the DESIGN.md spacing scale", () => {
    expect([...tokenSteps()].sort((a, b) => Number(a) - Number(b))).toEqual([
      "1", "2", "3", "4", "6", "8", "12", "16", "24",
    ]);
  });

  test("every spacing class uses a step from the scale", () => {
    const steps = tokenSteps();
    const offending: string[] = [];
    for (const dir of SOURCE_DIRS) {
      for (const file of sourceFiles(join(WEB, dir))) {
        const text = readFileSync(file, "utf-8");
        for (const match of text.matchAll(CLASS)) {
          if (match[2] !== "0" && !steps.has(match[2])) {
            offending.push(`${relative(WEB, file)}: ${match[0]}`);
          }
        }
      }
    }
    expect(offending).toEqual([]);
  });
});

describe("design pass rules (DESIGN.md sections 1, 3 and 4)", () => {
  const css = readFileSync(join(WEB, "app", "globals.css"), "utf-8");
  const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));

  test("reduced motion turns page morphs into an instant swap", () => {
    for (const pseudo of ["::view-transition-group(*)", "::view-transition-old(*)", "::view-transition-new(*)"]) {
      expect(reduced).toContain(pseudo);
    }
    expect(reduced).toMatch(/animation: none !important/);
  });

  test("the search box's clear button is ink, not the browser's blue", () => {
    const rule = css.slice(css.indexOf("::-webkit-search-cancel-button"));
    expect(rule.slice(0, rule.indexOf("}"))).toContain("background-color: var(--color-ink)");
  });

  test("no label is cut off with an ellipsis: text wraps instead", () => {
    const offending: string[] = [];
    for (const dir of SOURCE_DIRS) {
      for (const file of sourceFiles(join(WEB, dir))) {
        if (/\btruncate\b/.test(readFileSync(file, "utf-8"))) offending.push(relative(WEB, file));
      }
    }
    expect(offending).toEqual([]);
  });
});

describe("scale on large screens (DESIGN.md, Type)", () => {
  const css = readFileSync(join(WEB, "app", "globals.css"), "utf-8");

  test("type, spacing and the heavy and medium rules are rem, so they scale together", () => {
    const sizes = [...css.matchAll(/@utility type-[\w-]+ \{[^}]*\}/g)].map((m) => m[0]);
    expect(sizes.length).toBeGreaterThanOrEqual(8);
    for (const block of sizes) {
      if (block.includes("cqi")) {
        // The poster sizes to its container, between rem bounds, so it still scales.
        expect(block).toMatch(/font-size: clamp\([\d.]+rem, [\d.]+cqi, [\d.]+rem\);/);
        continue;
      }
      expect(block).toMatch(/font-size: [\d.]+rem;/);
      expect(block).toMatch(/line-height: [\d.]+rem;/);
    }
    expect([...css.matchAll(/--spacing-\d+: ([^;]+);/g)].every((m) => m[1].endsWith("rem"))).toBe(true);
    expect(css).toMatch(/--rule-heavy: [\d.]+rem;/);
    expect(css).toMatch(/--rule-medium: [\d.]+rem;/);
  });

  test("the base grows at 1600 and 2200 px, as a percentage", () => {
    expect(css).toMatch(/min-width: 1600px\)\s*\{\s*html\s*\{\s*font-size: 112.5%;/);
    expect(css).toMatch(/min-width: 2200px\)\s*\{\s*html\s*\{\s*font-size: 125%;/);
  });
});

describe("the warm page and ink bands (DESIGN.md, Colour)", () => {
  const css = readFileSync(join(WEB, "app", "globals.css"), "utf-8");
  const colour = (name: string) => {
    const match = css.match(new RegExp(`--color-${name}: (#[0-9a-f]{6});`));
    if (!match) throw new Error(`no --color-${name}`);
    return match[1];
  };
  const luminance = (hex: string) => {
    const channel = (i: number) => {
      const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
  };
  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(colour(a)), luminance(colour(b))].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };

  test("text meets WCAG AA on both grounds", () => {
    expect(contrast("ink", "page")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("ink-muted", "page")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("paper", "ink")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("paper-muted", "ink")).toBeGreaterThanOrEqual(4.5);
  });

  test("the focus ring shows on both grounds (3:1 for a focus indicator)", () => {
    expect(contrast("focus", "page")).toBeGreaterThanOrEqual(3);
    expect(contrast("focus-inverse", "ink")).toBeGreaterThanOrEqual(3);
    // On ink the inverse ring is far clearer than the usual blue (8:1 against 3.5:1).
    expect(contrast("focus-inverse", "ink")).toBeGreaterThan(2 * contrast("focus", "ink"));
  });

  test("the ticker stands still under reduced motion", () => {
    const reduced = css.slice(css.indexOf("prefers-reduced-motion: reduce"));
    expect(reduced).toMatch(/\.animate-ticker\s*\{\s*animation: none !important;/);
  });
});
