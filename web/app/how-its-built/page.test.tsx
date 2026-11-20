import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { STAGES } from "@/components/built/architecture";
import { AUTHOR, BUILT, EVAL_RESULTS, REPO_URL } from "@/lib/copy";

import HowItsBuiltPage, { metadata } from "./page";

afterEach(cleanup);

test("says who built it and links to them and the code", () => {
  render(<HowItsBuiltPage />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("How LabelLens is built");
  expect(screen.getByText(/I’m Aditya Kanbargi/)).toBeDefined();
  expect(screen.getByRole("link", { name: "LinkedIn" }).getAttribute("href")).toBe(AUTHOR.linkedin);
  expect(screen.getByRole("link", { name: "The code" }).getAttribute("href")).toBe(REPO_URL);
  expect(metadata.title).toBe("How it’s built");
});

test("the architecture reads in order, from the source to the apps", () => {
  render(<HowItsBuiltPage />);
  const diagram = screen.getByRole("list", { name: /Architecture/ });
  const stages = within(diagram)
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent);
  expect(stages).toEqual(["Source", "Pipeline", "Storage", "API", "Apps"]);
  for (const part of STAGES.flatMap((stage) => stage.parts)) {
    expect(within(diagram).getByText(part.name)).toBeDefined();
  }
});

test("every eval is listed with a link to its report", () => {
  render(<HowItsBuiltPage />);
  for (const result of EVAL_RESULTS) {
    const link = screen.getByRole("link", { name: result.name });
    expect(link.getAttribute("href")).toBe(`${REPO_URL}/blob/main/${result.file}`);
    expect(screen.getByText(result.headline)).toBeDefined();
  }
  const evals = BUILT.facts.find((fact) => fact.label.startsWith("evals"));
  expect(evals?.value).toBe(String(EVAL_RESULTS.length));
});

test("credits Claude Code as help, with the author's review", () => {
  render(<HowItsBuiltPage />);
  const section = screen.getByRole("heading", { name: "How I worked" }).closest("section")!;
  expect(section.textContent).toContain("with the help of Claude Code");
  expect(section.textContent).toContain("a pull request that I reviewed before merging");
});
