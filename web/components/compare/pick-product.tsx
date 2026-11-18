"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { GradeChip } from "@/components/label/primitives";
import { ApiError, searchProducts, type SearchResult } from "@/lib/api";
import { compareHref } from "@/lib/compare";
import { NO_MATCH, WAKING_UP } from "@/lib/copy";

const DEBOUNCE_MS = 150;

type Outcome = { q: string; results: SearchResult[] } | { q: string; error: string };

/**
 * Picks a product to compare: each result links to the comparison with it added. `chosen` holds
 * the barcodes already picked, which are left out of the results.
 */
export function PickProduct({ chosen, label }: { chosen: string[]; label: string }) {
  const [query, setQuery] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const inputId = useId();
  const statusId = useId();
  const q = query.trim();

  useEffect(() => {
    if (!q) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchProducts(q, { limit: 8, signal: controller.signal })
        .then((body) => setOutcome({ q, results: body.results }))
        .catch((error: unknown) => {
          if ((error as { name?: string })?.name === "AbortError") return;
          const message = error instanceof ApiError && !error.wakingUp ? error.message : WAKING_UP;
          setOutcome({ q, error: message });
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  const current = q && outcome?.q === q ? outcome : null;
  const results =
    current && "results" in current ? current.results.filter((r) => !chosen.includes(r.code)) : [];

  return (
    <div>
      <label htmlFor={inputId} className="type-data-label block pb-2">
        {label}
      </label>
      <input
        id={inputId}
        type="search"
        autoComplete="off"
        spellCheck={false}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Name, brand or barcode"
        aria-describedby={statusId}
        className="panel type-body block w-full rounded-none px-4 py-3 placeholder:text-ink-muted"
      />
      <div id={statusId} role="status" aria-live="polite" className="type-small pt-3">
        {current && "error" in current && <p>{current.error}</p>}
        {current && "results" in current && results.length === 0 && <p>{NO_MATCH}</p>}
      </div>
      {results.length > 0 && (
        <ol aria-label="Products to compare">
          {results.map((product) => (
            <li key={product.code}>
              <Link
                href={compareHref([...chosen, product.code])}
                className="flex items-center justify-between gap-4 border-b border-rule-light py-3 no-underline"
              >
                <span className="min-w-0">
                  <span className="type-data-value block break-words">{product.name}</span>
                  <span className="type-small block break-words text-ink-muted">
                    {product.brand ?? "Brand not listed"}
                  </span>
                </span>
                <GradeChip grade={product.nutriscore_grade} />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
