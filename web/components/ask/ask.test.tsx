import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { AskAnswer, AskStep } from "@/lib/ask";
import { ASK_AI_NOTE, ASK_REFUSED_NOTE, ASK_REPLAY_NOTE } from "@/lib/copy";

const askQuestion = vi.fn();
vi.mock("@/lib/ask", async (original) => ({
  ...(await original<typeof import("@/lib/ask")>()),
  askQuestion: (...args: unknown[]) => askQuestion(...args),
}));

let reducedMotion = false;
vi.mock("motion/react", async (original) => ({
  ...(await original<typeof import("motion/react")>()),
  useReducedMotion: () => reducedMotion,
}));

const { AskPanel } = await import("./ask-panel");
const { AskFailure, RateLimited } = await import("@/lib/ask");

const source = {
  name: "Open Food Facts" as const,
  url: "https://world.openfoodfacts.org",
  licence: "ODbL-1.0" as const,
  licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
  snapshot_date: "2026-11-17",
};

const steps: AskStep[] = [
  { index: 1, tool: "query_sql", summary: "Cereals under 5 g sugar", row_count: 12, duration_ms: 180 },
  { index: 2, tool: "search_explainers", summary: "What colours are", row_count: 1, duration_ms: 90 },
];

const answer: AskAnswer = {
  text: "Two fit [1], and one more [2].\n- Oats [1]\n- Bran [3]",
  citations: [
    { n: 1, kind: "row", ref: "001", label: "Oats (Quaker)", url: "/products/001" },
    { n: 2, kind: "node", ref: "Product:002", label: "Bran", url: "/graph?code=002" },
    { n: 3, kind: "explainer", ref: "en:e150a", label: "Caramel colour", url: null },
  ],
  refused: false,
  replay: false,
  source,
};

/** askQuestion that streams the given steps, then resolves or rejects. */
function scripted(result: AskAnswer | Error, sent: AskStep[] = steps) {
  askQuestion.mockImplementation(async (...args: unknown[]) => {
    const options = args[1] as { onStep?: (s: AskStep) => void };
    for (const step of sent) options.onStep?.(step);
    if (result instanceof Error) throw result;
    return result;
  });
}

async function ask(text: string) {
  fireEvent.change(screen.getByLabelText("Your question"), { target: { value: text } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  });
}

beforeEach(() => {
  askQuestion.mockReset();
  reducedMotion = false;
});
afterEach(cleanup);

describe("AskPanel", () => {
  test("shows each step as a label row, then the answer with linked citations", async () => {
    scripted(answer);
    render(<AskPanel />);
    await ask("cereals under 5 g sugar");

    expect(askQuestion.mock.calls[0][0]).toBe("cereals under 5 g sugar");
    const panel = screen.getByRole("region", { name: "Steps" });
    // Collapsed once the answer is in; the button opens it.
    fireEvent.click(within(panel).getByRole("button", { name: "Show steps (2)" }));
    const rows = within(panel).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      "1. Searched the products12 rowsCereals under 5 g sugar · 180 ms",
      "2. Searched the explainers1 rowWhat colours are · 90 ms",
    ]);

    const answerRegion = screen.getByRole("region", { name: "Answer" });
    const source1 = within(answerRegion).getAllByRole("link", { name: "Source 1: Oats (Quaker)" });
    expect(source1[0].getAttribute("href")).toBe("/products/001");
    expect(within(answerRegion).getByRole("link", { name: "Source 2: Bran" }).getAttribute("href")).toBe(
      "/graph?code=002",
    );
    // An explainer has no page: its marker jumps to the source list.
    expect(within(answerRegion).getByRole("link", { name: "Source 3: Caramel colour" }).getAttribute("href")).toBe(
      "#source-3",
    );
    expect(within(answerRegion).getAllByRole("listitem").length).toBeGreaterThanOrEqual(2 + 3);
    expect(screen.getByText("Explainer, written by AI")).toBeTruthy();
    expect(screen.getByText(ASK_AI_NOTE)).toBeTruthy();
  });

  test("steps stay open while the agent works", async () => {
    let finish: (a: AskAnswer) => void = () => {};
    askQuestion.mockImplementation(
      (_q: string, options: { onStep?: (s: AskStep) => void }) =>
        new Promise<AskAnswer>((resolve) => {
          options.onStep?.(steps[0]);
          finish = resolve;
        }),
    );
    render(<AskPanel />);
    await ask("cereals");
    const panel = screen.getByRole("region", { name: "Steps" });
    expect(within(panel).getByText("1. Searched the products")).toBeTruthy();
    expect(within(panel).getByText("Working…")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Asking…" }).hasAttribute("disabled")).toBe(true);
    await act(async () => finish(answer));
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
  });

  test("a refusal and a replay are labelled", async () => {
    scripted({ ...answer, text: "LabelLens can't give that advice.", citations: [], refused: true }, []);
    render(<AskPanel />);
    await ask("is this ok for my diabetes");
    expect(screen.getByText(ASK_REFUSED_NOTE)).toBeTruthy();
    expect(screen.getByText("Answered without looking anything up.")).toBeTruthy();

    cleanup();
    scripted({ ...answer, replay: true });
    render(<AskPanel />);
    await ask("cereals");
    expect(screen.getByText(ASK_REPLAY_NOTE)).toBeTruthy();
  });

  test("errors say what failed and what to do", async () => {
    scripted(new RateLimited("That's 10 questions this hour from here.", 600));
    render(<AskPanel />);
    await ask("cereals");
    expect(screen.getByRole("alert").textContent).toBe(
      "That's 10 questions this hour from here. Try again in about 10 minutes.",
    );

    cleanup();
    scripted(new AskFailure("timeout", "That took too long, so it was stopped."), [steps[0]]);
    render(<AskPanel />);
    await ask("cereals");
    expect(screen.getByRole("alert").textContent).toBe("That took too long, so it was stopped.");
    // The steps that ran are still shown.
    expect(screen.getByText("1. Searched the products")).toBeTruthy();
  });

  test("a failure before any step shows the message without an empty steps panel", async () => {
    scripted(new RateLimited("That's 10 questions this hour from here.", 600), []);
    render(<AskPanel />);
    await ask("cereals");
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Steps" })).toBeNull();
  });

  test("an example question asks straight away", async () => {
    scripted(answer);
    render(<AskPanel />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Healthier swaps for Nacho Cheese Doritos" }));
    });
    expect(askQuestion.mock.calls[0][0]).toBe("Healthier swaps for Nacho Cheese Doritos");
  });

  test("Show steps names the list it opens and closes", async () => {
    scripted(answer);
    render(<AskPanel />);
    await ask("cereals");
    const toggle = screen.getByRole("button", { name: "Show steps (2)" });
    const list = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
    expect(list).not.toBeNull();
    expect(list!.hidden).toBe(true);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    fireEvent.click(toggle);
    expect(list!.hidden).toBe(false);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(within(list!).getAllByRole("listitem")).toHaveLength(2);
  });

  test("step rows wipe in, unless the reader prefers reduced motion", async () => {
    const wiping = () =>
      screen.getAllByRole("listitem").filter((row) => row.querySelector("[style*='clip-path']")).length;

    scripted(answer, [steps[0]]);
    render(<AskPanel />);
    await ask("cereals");
    fireEvent.click(screen.getByRole("button", { name: "Show steps (1)" }));
    expect(wiping()).toBe(1);

    cleanup();
    reducedMotion = true;
    scripted(answer, [steps[0]]);
    render(<AskPanel />);
    await ask("cereals");
    fireEvent.click(screen.getByRole("button", { name: "Show steps (1)" }));
    expect(screen.getByText("1. Searched the products")).toBeTruthy();
    expect(wiping()).toBe(0);
  });

  test("Enter submits; a question under three characters does not", async () => {
    scripted(answer);
    render(<AskPanel />);
    const box = screen.getByLabelText("Your question");
    fireEvent.change(box, { target: { value: "hi" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(askQuestion).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "oats?" } });
    await act(async () => {
      fireEvent.keyDown(box, { key: "Enter" });
    });
    expect(askQuestion).toHaveBeenCalledTimes(1);
  });
});
