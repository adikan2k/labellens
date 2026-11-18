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
