"use client";

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { DataRow, Rule } from "@/components/label/primitives";
import { ApiError } from "@/lib/api";
import {
  AskFailure,
  RateLimited,
  TOOL_NAMES,
  askQuestion,
  splitCitations,
  type AskAnswer,
  type AskStep,
  type Citation,
} from "@/lib/ask";
import {
  ASK_AI_NOTE,
  ASK_EXAMPLES,
  ASK_REFUSED_NOTE,
  ASK_REPLAY_NOTE,
  ASK_UNAVAILABLE,
  ASK_WAKING_UP,
  retryIn,
} from "@/lib/copy";

type State =
  | { kind: "idle" }
  | { kind: "running"; question: string; steps: AskStep[] }
  | { kind: "done"; question: string; steps: AskStep[]; answer: AskAnswer }
  | { kind: "error"; question: string; steps: AskStep[]; message: string };

const MAX_LENGTH = 500;
const EASE_OUT = [0.2, 0, 0, 1] as const;

function failureMessage(error: unknown): string {
  if (error instanceof RateLimited) {
    return error.message.includes("Try again")
      ? error.message
      : `${error.message} ${retryIn(error.retryAfterSeconds)}`;
  }
  if (error instanceof AskFailure) return error.message;
  if (error instanceof ApiError) {
    if (error.status === 503 && error.message.includes("not configured")) return ASK_UNAVAILABLE;
    if (error.status === 503) return ASK_WAKING_UP;
    return error.message;
  }
  return "Something went wrong answering that. Try again.";
}

/** Ask a question: the box, the agent's steps as label rows, then the cited answer. */
export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<State>({ kind: "idle" });
  const [showSteps, setShowSteps] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const inputId = useId();
  const running = state.kind === "running";

  async function ask(text: string) {
    const q = text.trim();
    if (q.length < 3 || running) return;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setShowSteps(false);
    let steps: AskStep[] = [];
    setState({ kind: "running", question: q, steps });
    try {
      const answer = await askQuestion(q, {
        signal: abort.signal,
        onStep: (step) => {
          steps = [...steps, step];
          setState({ kind: "running", question: q, steps });
        },
      });
      setState({ kind: "done", question: q, steps, answer });
    } catch (error) {
      if ((error as { name?: string } | null)?.name === "AbortError") return;
      setState({ kind: "error", question: q, steps, message: failureMessage(error) });
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  const steps = state.kind === "idle" ? [] : state.steps;
  const stepsOpen = state.kind !== "done" || showSteps || steps.length === 0;

  return (
    <div className="max-w-measure">
      <form onSubmit={onSubmit} aria-busy={running}>
        <label htmlFor={inputId} className="type-data-label block pb-1">
          Your question
        </label>
        <textarea
          id={inputId}
          rows={2}
          maxLength={MAX_LENGTH}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void ask(question);
            }
          }}
          placeholder="Which cereals have under 5 g sugar?"
          className="panel type-body block w-full resize-y rounded-none px-3 py-2 placeholder:text-ink-muted"
        />
        <div className="flex items-baseline justify-between gap-4 pt-3">
          <button
            type="submit"
            disabled={running || question.trim().length < 3}
            className="type-data-value shrink-0 cursor-pointer rounded-control bg-ink px-4 py-2 text-paper disabled:cursor-default disabled:bg-ink-muted"
          >
            {running ? "Asking…" : "Ask"}
          </button>
          <span className="type-small hidden text-ink-muted sm:inline">
            Enter to ask, Shift+Enter for a new line
          </span>
        </div>
      </form>
      <div className="pt-6">
        <p className="type-small text-ink-muted">Or try one of these:</p>
        <ul>
          {ASK_EXAMPLES.map((example) => (
            <li key={example} className="border-b border-rule-light py-2">
              <button
                type="button"
                disabled={running}
                className="type-small cursor-pointer text-left underline underline-offset-2 disabled:cursor-default disabled:text-ink-muted"
                onClick={() => {
                  setQuestion(example);
                  void ask(example);
                }}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div role="status" aria-live="polite" className="sr-only">
        {running && (steps.length ? `Step ${steps.length}: ${steps[steps.length - 1].summary}` : "Looking it up")}
        {state.kind === "done" && "Answer ready"}
        {state.kind === "error" && state.message}
      </div>

      {state.kind !== "idle" && (
        <section aria-label="Steps" className="panel mt-8 px-4 pt-3 pb-4">
          <Rule weight="heavy" />
          <div className="flex items-baseline justify-between gap-4 pt-2 pb-1">
            <h2 className="type-heading">Steps</h2>
            {state.kind === "done" && steps.length > 0 && (
              <button
                type="button"
                aria-expanded={showSteps}
                onClick={() => setShowSteps((open) => !open)}
                className="type-small cursor-pointer underline underline-offset-2"
              >
                {showSteps ? "Hide steps" : `Show steps (${steps.length})`}
              </button>
            )}
          </div>
          {stepsOpen && (
            <>
              <Rule weight="medium" />
              <ol>
                {steps.map((step) => (
                  <StepRow key={step.index} step={step} />
                ))}
              </ol>
              {running && (
                <p className="type-data-label py-2 text-ink-muted">
                  {steps.length === 0 ? "Reading the question…" : "Working…"}
                </p>
              )}
              {state.kind === "done" && steps.length === 0 && (
                <p className="type-small py-2 text-ink-muted">Answered without looking anything up.</p>
              )}
            </>
          )}
          {stepsOpen && <Rule weight="heavy" className="mt-2" />}
        </section>
      )}

      {state.kind === "error" && (
        <p className="type-body pt-6" role="alert">
          {state.message}
        </p>
      )}

      {state.kind === "done" && <AnswerView answer={state.answer} />}
    </div>
  );
}

function StepRow({ step }: { step: AskStep }) {
  const reduced = useReducedMotion();
  const rows = `${step.row_count} ${step.row_count === 1 ? "row" : "rows"}`;
  const content = (
    <>
      <DataRow label={`${step.index}. ${TOOL_NAMES[step.tool]}`} value={rows} />
      <p className="type-small pb-2 text-ink-muted">
        {step.summary} · {step.duration_ms.toLocaleString("en-US")} ms
      </p>
    </>
  );
  return (
    <li className="border-b border-ink last:border-b-0">
      {reduced ? (
        content
      ) : (
        <motion.div
          initial={{ clipPath: "inset(0 100% 0 0)" }}
          animate={{ clipPath: "inset(0 0% 0 0)" }}
          transition={{ duration: 0.24, ease: EASE_OUT }}
        >
          {content}
        </motion.div>
      )}
    </li>
  );
}

const KIND_LABEL: Record<Citation["kind"], string> = {
  row: "Product data",
  node: "Food graph",
  explainer: "Explainer, written by AI",
};

function CitationLink({ n, citation }: { n: number; citation: Citation | undefined }) {
  if (!citation) return <>[{n}]</>;
  const label = `Source ${n}: ${citation.label}`;
  const className = "type-small align-baseline no-underline hover:underline";
  return citation.url ? (
    <Link href={citation.url} aria-label={label} className={className}>
      [{n}]
    </Link>
  ) : (
    <a href={`#source-${n}`} aria-label={label} className={className}>
      [{n}]
    </a>
  );
}

/** The answer's text with its [n] markers as links, keeping "- " lines as a list. */
function AnswerText({ text, citations }: { text: string; citations: Citation[] }) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const inline = (line: string) =>
    splitCitations(line).map((part, i) =>
      typeof part === "number" ? <CitationLink key={i} n={part} citation={byN.get(part)} /> : part,
    );
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`l${blocks.length}`} className="list-disc space-y-1 pl-6">
          {list.map((item, i) => (
            <li key={i}>{inline(item)}</li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const line of text.split("\n")) {
    if (line.startsWith("- ")) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (line.trim()) blocks.push(<p key={`p${blocks.length}`}>{inline(line)}</p>);
  }
  flush();
  return <div className="type-body space-y-3">{blocks}</div>;
}

function AnswerView({ answer }: { answer: AskAnswer }) {
  return (
    <section aria-labelledby="answer-title" className="pt-8">
      <h2 id="answer-title" className="type-heading pb-2">
        Answer
      </h2>
      {answer.replay && <p className="type-small pb-2">{ASK_REPLAY_NOTE}</p>}
      {answer.refused && <p className="type-small pb-2">{ASK_REFUSED_NOTE}</p>}
      <AnswerText text={answer.text} citations={answer.citations} />
      {answer.citations.length > 0 && (
        <div className="pt-6">
          <h3 className="type-data-label pb-1">Sources</h3>
          <Rule weight="thin" />
          <ol>
            {answer.citations.map((c) => (
              <li
                key={c.n}
                id={`source-${c.n}`}
                className="type-small flex gap-3 border-b border-rule-light py-2"
              >
                <span className="type-data-value shrink-0 tabular-nums">{c.n}</span>
                <span className="min-w-0">
                  {c.url ? <Link href={c.url}>{c.label}</Link> : <span>{c.label}</span>}
                  <span className="block text-ink-muted">{KIND_LABEL[c.kind]}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <p className="type-small pt-4 text-ink-muted">{ASK_AI_NOTE}</p>
    </section>
  );
}
