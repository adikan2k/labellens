"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";

import { GradeChip } from "@/components/label/primitives";
import { searchProducts, type SearchResult } from "@/lib/api";

const DEBOUNCE_MS = 150;

/** Find a product to centre the graph on. Results link to /graph?code=. */
export function GraphSearch() {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<{ q: string; results: SearchResult[] } | null>(null);
  const inputId = useId();
  const q = query.trim();

  useEffect(() => {
    if (!q) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      searchProducts(q, { limit: 6, signal: controller.signal }).then(
        (response) => setFound({ q, results: response.results }),
        () => setFound({ q, results: [] }),
      );
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [q]);

  const results = q && found?.q === q ? found.results : [];
  return (
    <div className="max-w-measure">
      <label htmlFor={inputId} className="type-data-label block pb-1">
        Centre the graph on another product
      </label>
      <input
        id={inputId}
        type="search"
        autoComplete="off"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Name, brand or barcode"
        className="panel type-body block w-full rounded-none px-3 py-2 placeholder:text-ink-muted"
      />
      {results.length > 0 && (
        <ol aria-label="Products to centre on">
          {results.map((product) => (
            <li key={product.code}>
              <Link
                href={`/graph?code=${product.code}`}
                onClick={() => setQuery("")}
                className="flex items-center justify-between gap-4 border-b border-rule-light py-2 no-underline"
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
