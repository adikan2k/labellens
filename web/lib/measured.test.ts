import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

import { EVAL_RESULTS, M, MEASURED } from "./measured";

// Vitest runs from web/ (pnpm -C web test); the reports and the README are at the repository root.
const repoRoot = resolve(process.cwd(), "..");
const read = (path: string) => readFileSync(resolve(repoRoot, path), "utf-8");

describe("measured numbers", () => {
  test.each(Object.entries(M))("%s is what its report prints", (_name, measure) => {
    expect(read(measure.file)).toContain(measure.evidence);
  });

  test.each(Object.entries(M))("%s: the report's text carries the value shown", (_name, measure) => {
    // "184 ms" is shown for a report that prints "184.0": compare the digits.
    const shown = measure.value.replace(/[^\d./]/g, "");
    expect(measure.evidence).toContain(shown);
  });

  test("the home page's numbers are the About page's numbers", () => {
    for (const m of MEASURED) {
      const about = EVAL_RESULTS.find((result) => result.file === m.file);
      expect(about, m.file).toBeDefined();
      // 29/30 is written out as "29 of 30" in a sentence.
      const inWords = m.value.replace("/", " of ");
      expect(about?.headline, m.file).toContain(inWords);
    }
  });

  test("the README shows the same four numbers", () => {
    const readme = read("README.md");
    for (const m of MEASURED) expect(readme, m.value).toContain(m.value);
  });
});
