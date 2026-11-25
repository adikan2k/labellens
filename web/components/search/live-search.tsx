"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, useSyncExternalStore, ViewTransition } from "react";

import { PackPhoto } from "@/components/label/pack-photo";
import { GradeChip } from "@/components/label/primitives";
import { ApiError, searchProducts, type SearchResult } from "@/lib/api";
import { NO_MATCH, SCAN, SEARCH_SLOW, SEARCH_SLOW_AFTER_MS, WAKING_UP } from "@/lib/copy";

import { BarcodeScanner } from "./barcode-scanner";

const DEBOUNCE_MS = 150;
const EXAMPLES = ["Cheerios", "Oreo", "Coca-Cola"];

/** The last finished search: its results, or what went wrong. */
type Outcome = { q: string; results: SearchResult[] } | { q: string; error: string };

/** The home page search: results appear while typing, as label rows. */
export function LiveSearch({ productCount }: { productCount: number | null }) {
  const [query, setQuery] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [attempt, setAttempt] = useState(0);
  // The query whose search has been running long enough to say why.
  const [slowFor, setSlowFor] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const statusId = useId();
  const q = query.trim();

  // State is only set when a request finishes; loading is derived below.
  useEffect(() => {
    if (!q) return;
    const controller = new AbortController();
    // Fires only when the search is still running: a finished one clears it below.
    const slow = setTimeout(() => setSlowFor(q), DEBOUNCE_MS + SEARCH_SLOW_AFTER_MS);
    const finish = (next: Outcome) => {
      clearTimeout(slow);
      setSlowFor(null);
      setOutcome(next);
    };
    const timer = setTimeout(() => {
      searchProducts(q, { limit: 10, signal: controller.signal })
        .then((body) => finish({ q, results: body.results }))
        .catch((error: unknown) => {
          if ((error as { name?: string })?.name === "AbortError") return;
          const message =
            error instanceof ApiError && !error.wakingUp ? error.message : WAKING_UP;
          finish({ q, error: message });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      clearTimeout(slow);
      controller.abort();
    };
  }, [q, attempt]);

  const current = q && outcome?.q === q ? outcome : null;
  const loading = q !== "" && current === null;
  // While the next results load, the previous ones stay on screen, dimmed.
  const shown = current ?? (loading ? outcome : null);
  const results = shown && "results" in shown ? shown.results : [];
  const state = !q
    ? { kind: "idle" as const }
    : current && "error" in current
      ? { kind: "error" as const, message: current.error }
      : { kind: loading ? ("loading" as const) : ("done" as const) };

  // Short enough to fit the box at 375 px; how to search goes in the line below it.
  const placeholder =
    productCount === null
      ? "Search US products"
      : `Search ${productCount.toLocaleString("en-US")} US products`;

  return (
    <div>
      <label htmlFor={inputId} className="sr-only">
        Search products
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="search"
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={placeholder}
        aria-describedby={statusId}
        className="panel type-heading block w-full rounded-none px-4 py-3 placeholder:text-ink-muted lg:py-4"
      />
      <p className="type-small pt-3 text-ink-muted">
        Name, brand or barcode. Try:{" "}
        {EXAMPLES.map((example, i) => (
          <span key={example}>
            <button
              type="button"
              className="cursor-pointer underline underline-offset-2"
              onClick={() => {
                setQuery(example);
                inputRef.current?.focus();
              }}
            >
              {example}
            </button>
            {i < EXAMPLES.length - 1 ? ", " : ""}
          </span>
        ))}
      </p>

      <ScanLine />

      <div id={statusId} role="status" aria-live="polite" className="type-small pt-6">
        {state.kind === "loading" && slowFor === q && <p>{SEARCH_SLOW}</p>}
        {state.kind === "done" && results.length === 0 && <p>{NO_MATCH}</p>}
        {state.kind === "done" && results.length > 0 && (
          <span className="sr-only">
            {results.length} {results.length === 1 ? "product" : "products"} found
          </span>
        )}
        {state.kind === "error" && (
          <p>
            {state.message}{" "}
            <button
              type="button"
              className="cursor-pointer underline underline-offset-2"
              onClick={() => {
                setOutcome(null);
                setAttempt((n) => n + 1);
              }}
            >
              Try again
            </button>
          </p>
        )}
      </div>

      {results.length > 0 && (
        <ol aria-label="Search results" className={state.kind === "loading" ? "opacity-60" : ""}>
          {results.map((product) => (
            <li key={product.code}>
              <ResultRow product={product} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

const noSubscription = () => () => {};
const hasCamera = () => typeof navigator.mediaDevices?.getUserMedia === "function";

/** "Scan a barcode", only where the browser can reach a camera, and its panel when open. */
function ScanLine() {
  // False on the server and during hydration, then the real answer: no mismatch, no effect.
  const camera = useSyncExternalStore(noSubscription, hasCamera, () => false);
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  if (!camera) return null;
  return (
    <>
      <p className="type-small pt-2">
        <button
          ref={buttonRef}
          type="button"
          aria-expanded={open}
          className="cursor-pointer underline underline-offset-2"
          onClick={() => setOpen((was) => !was)}
        >
          {SCAN.button}
        </button>{" "}
        <Link href="/label">{SCAN.orPhotograph}</Link>
      </p>
      {open && (
        <BarcodeScanner
          onClose={() => {
            setOpen(false);
            buttonRef.current?.focus();
          }}
        />
      )}
    </>
  );
}

function ResultRow({ product }: { product: SearchResult }) {
  return (
    <Link
      href={`/product/${product.code}`}
      className="flex items-center justify-between gap-4 border-b border-rule-light py-3 no-underline"
    >
      <span className="flex min-w-0 items-center gap-3">
        <PackPhoto src={product.image_url} name={product.name} size="row" />
        <span className="min-w-0">
          <ViewTransition name={`name-${product.code}`} share="morph" default="none">
            <span className="type-data-value block break-words">{product.name}</span>
          </ViewTransition>
          <span className="type-small block break-words text-ink-muted">
            {product.brand ?? "Brand not listed"}
          </span>
        </span>
      </span>
      <ViewTransition name={`grade-${product.code}`} share="morph" default="none">
        <span className="shrink-0">
          <GradeChip grade={product.nutriscore_grade} />
        </span>
      </ViewTransition>
    </Link>
  );
}
