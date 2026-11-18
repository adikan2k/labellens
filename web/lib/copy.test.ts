import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, test } from "vitest";

import { ASK_PRIVACY_NOTE, EVAL_RESULTS, MCP_URL, repoFileUrl } from "./copy";

// Vitest runs from web/ (pnpm -C web test); the eval results live at the repository root.
const repoRoot = resolve(process.cwd(), "..");

describe("ask privacy note", () => {
  test("names every service a question goes to", () => {
    for (const name of ["Anthropic", "Voyage AI", "Langfuse"]) {
      expect(ASK_PRIVACY_NOTE).toContain(name);
    }
  });

  test("asks for no personal details", () => {
    expect(ASK_PRIVACY_NOTE).toMatch(/Don’t include personal details\.$/);
  });

  test("promises no deletion that Langfuse Hobby does not do", () => {
    expect(ASK_PRIVACY_NOTE).not.toMatch(/\d+ days/);
  });
});

describe("About: how it's measured", () => {
  test("every eval in the list has its results file in the repository", () => {
    for (const result of EVAL_RESULTS) {
      expect(existsSync(resolve(repoRoot, result.file)), result.file).toBe(true);
    }
  });

  test("every headline carries a number", () => {
    for (const result of EVAL_RESULTS) {
      expect(result.headline, result.name).toMatch(/\d/);
    }
  });

  test("links point at the file on GitHub", () => {
    expect(repoFileUrl("evals/results/ask_agent.md")).toBe(
      "https://github.com/adikan2k/labellens/blob/main/evals/results/ask_agent.md",
    );
  });

  test("the ask agent's headline is the eval's fact score", () => {
    const ask = EVAL_RESULTS.find((result) => result.file.endsWith("ask_agent.md"));
    expect(ask?.headline).toContain("0.98");
    expect(ask?.headline).toContain("0.26");
  });
});

describe("About: use it in Claude", () => {
  test("the connector address is the public API's MCP endpoint", () => {
    expect(MCP_URL).toBe("https://labellens-api-1036759996795.us-east4.run.app/mcp");
  });
});
