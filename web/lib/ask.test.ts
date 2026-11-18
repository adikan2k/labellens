import { afterEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "./api";
import { AskFailure, RateLimited, askQuestion, parseSse, splitCitations, type AskAnswer } from "./ask";
import { WAKING_UP } from "./copy";

afterEach(() => {
  vi.unstubAllGlobals();
});

const answer: AskAnswer = {
  text: "Two cereals [1] and [2].",
  citations: [
    { n: 1, kind: "row", ref: "1", label: "Oats", url: "/products/1" },
    { n: 2, kind: "node", ref: "Product:2", label: "Bran", url: "/graph?code=2" },
  ],
  refused: false,
  replay: false,
  source: {
    name: "Open Food Facts",
    url: "https://world.openfoodfacts.org",
    licence: "ODbL-1.0",
    licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
    snapshot_date: "2026-11-17",
  },
};

function sse(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** A streamed response whose body arrives in the given chunks. */
function streamed(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function stubFetch(response: Response | Error) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    if (response instanceof Error) throw response;
    return response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("parseSse", () => {
  test("keeps an unfinished event for the next chunk", () => {
    const { events, rest } = parseSse('event: step\ndata: {"a":1}\n\nevent: ans');
    expect(events).toEqual([{ event: "step", data: '{"a":1}' }]);
    expect(rest).toBe("event: ans");
  });

  test("accepts CRLF line endings and multi-line data", () => {
    const { events } = parseSse("event: x\r\ndata: one\r\ndata: two\r\n\r\n");
    expect(events).toEqual([{ event: "x", data: "one\ntwo" }]);
  });
});

describe("askQuestion", () => {
  test("posts the question, reports steps as they arrive, resolves with the answer", async () => {
    const step = { index: 1, tool: "query_sql", summary: "Cereals", row_count: 2, duration_ms: 90 };
    const whole = sse("step", step) + sse("answer", answer);
    // Chunks split mid-event and mid-character (é is two bytes in UTF-8 but one JS char here).
    const fetchMock = stubFetch(streamed([whole.slice(0, 17), whole.slice(17, 60), whole.slice(60)]));
    const steps: unknown[] = [];
    await expect(askQuestion("cereals?", { onStep: (s) => steps.push(s) })).resolves.toEqual(answer);
    expect(steps).toEqual([step]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/ask");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ question: "cereals?" });
  });

  test("an error event rejects with its code", async () => {
    stubFetch(streamed([sse("error", { code: "timeout", message: "That took too long." })]));
    const error = await askQuestion("x?").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(AskFailure);
    expect((error as AskFailure).code).toBe("timeout");
  });

  test("a stream that ends without an answer is internal", async () => {
    stubFetch(streamed([sse("step", { index: 1 })]));
    const error = await askQuestion("x?").catch((e: unknown) => e);
    expect((error as AskFailure).code).toBe("internal");
  });

  test("429 carries the message and Retry-After", async () => {
    stubFetch(
      new Response(JSON.stringify({ detail: "That's 10 questions this hour from here." }), {
        status: 429,
        headers: { "Retry-After": "720", "Content-Type": "application/json" },
      }),
    );
    const error = await askQuestion("x?").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(RateLimited);
    expect((error as RateLimited).retryAfterSeconds).toBe(720);
    expect((error as RateLimited).message).toContain("10 questions");
  });

  test("no response at all is waking up", async () => {
    stubFetch(new TypeError("fetch failed"));
    const error = await askQuestion("x?").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe(WAKING_UP);
  });
});

test("splitCitations separates [n] markers from text", () => {
  expect(splitCitations("A [1] and B [2][3].")).toEqual(["A ", 1, " and B ", 2, 3, "."]);
  expect(splitCitations("No sources.")).toEqual(["No sources."]);
});
