/**
 * POST /ask: read the server-sent events with fetch (EventSource cannot POST).
 *
 * `step` events arrive as each tool call finishes and go to `onStep`; the promise resolves
 * with the `answer`. An `error` event rejects with AskFailure (its contract code); an HTTP
 * error rejects with ApiError (429 carries Retry-After, 503 is waking up or not configured).
 */
import { API_URL, ApiError } from "./api";
import type { components } from "./api-types";
import { WAKING_UP } from "./copy";

type Schemas = components["schemas"];
export type AskStep = Schemas["AskStep"];
export type AskAnswer = Schemas["AskAnswer"];
export type Citation = Schemas["Citation"];
export type AskErrorCode = Schemas["AskError"]["code"];

export class AskFailure extends Error {
  constructor(
    readonly code: AskErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "AskFailure";
  }
}

export class RateLimited extends ApiError {
  constructor(
    message: string,
    readonly retryAfterSeconds: number | null,
  ) {
    super(429, message);
    this.name = "RateLimited";
  }
}

export type SseEvent = { event: string; data: string };

/** Split a growing buffer into complete events; returns them and the unfinished rest. */
export function parseSse(buffer: string): { events: SseEvent[]; rest: string } {
  const normalised = buffer.replace(/\r\n/g, "\n");
  const blocks = normalised.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

export async function askQuestion(
  question: string,
  options: { onStep?: (step: AskStep) => void; signal?: AbortSignal } = {},
): Promise<AskAnswer> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question }),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as { name?: string } | null)?.name === "AbortError") throw error;
    throw new ApiError(503, WAKING_UP);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as Schemas["Error"] | null;
    const message = body?.detail ?? `Request failed (${response.status}).`;
    if (response.status === 429) {
      const retry = Number(response.headers.get("Retry-After"));
      throw new RateLimited(message, Number.isFinite(retry) && retry > 0 ? retry : null);
    }
    throw new ApiError(response.status, message);
  }
  if (!response.body) throw new AskFailure("internal", "The answer did not arrive. Try again.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
    const { events, rest } = parseSse(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const { event, data } of events) {
      const payload = JSON.parse(data) as unknown;
      if (event === "step") options.onStep?.(payload as AskStep);
      else if (event === "answer") return payload as AskAnswer;
      else if (event === "error") {
        const error = payload as Schemas["AskError"];
        throw new AskFailure(error.code, error.message);
      }
    }
    if (done) break;
  }
  throw new AskFailure("internal", "The answer was cut off. Try again.");
}

/** Plain words for a tool, as the steps panel shows it. */
export const TOOL_NAMES: Record<AskStep["tool"], string> = {
  query_sql: "Searched the products",
  query_graph: "Looked up the food graph",
  search_explainers: "Searched the explainers",
};

/** "[1]" markers in an answer, split out so they can become links. */
export function splitCitations(text: string): Array<string | number> {
  const parts: Array<string | number> = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+)\]/g)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    parts.push(Number(match[1]));
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
