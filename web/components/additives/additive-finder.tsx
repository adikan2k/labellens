"use client";

import Link from "next/link";
import { useDeferredValue, useId, useState } from "react";

import { additiveHref, filterAdditives } from "@/lib/additives";
import type { AdditiveListItem } from "@/lib/api";
import { ADDITIVES } from "@/lib/copy";
import { formatCount } from "@/lib/format";

/** The guide's list: filters by name or E number as you type, and to flagged ones. */
export function AdditiveFinder({ additives }: { additives: AdditiveListItem[] }) {
  const [query, setQuery] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const deferred = useDeferredValue(query);
  const inputId = useId();
  const statusId = useId();
  const shown = filterAdditives(additives, deferred, flaggedOnly);

  return (
    <div className="pt-6">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label htmlFor={inputId} className="sr-only">
          {ADDITIVES.findLabel}
        </label>
        <input
          id={inputId}
          type="text"
          inputMode="search"
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={ADDITIVES.findPlaceholder}
          aria-describedby={statusId}
          className="panel type-heading block w-full max-w-measure rounded-none px-4 py-3 placeholder:text-ink-muted"
        />
        <label className="type-small flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={flaggedOnly}
            onChange={(event) => setFlaggedOnly(event.target.checked)}
            className="h-4 w-4 accent-ink"
          />
          {ADDITIVES.flaggedOnly}
        </label>
      </div>
      <p id={statusId} role="status" className="type-small pt-3 pb-2 text-ink-muted">
        {ADDITIVES.shown(shown.length, additives.length)}
      </p>
      {shown.length === 0 ? (
        <p className="type-body pt-3">{ADDITIVES.none}</p>
      ) : (
        <ol className="border-t border-rule-light">
          {shown.map((item) => (
            <li key={item.additive_id} className="border-b border-rule-light">
              <Link
                href={additiveHref(item.additive_id)}
                className="flex items-baseline justify-between gap-4 py-2 no-underline"
              >
                <span className="min-w-0">
                  <span className="type-data-label block break-words">
                    {item.e_number && (
                      <span className="type-data-value pr-2">{item.e_number}</span>
                    )}
                    {item.name}
                  </span>
                  <span className="type-small block text-ink-muted">
                    {[item.function, item.flagged ? ADDITIVES.flagged : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <span className="type-data-value shrink-0 tabular-nums">
                  {formatCount(item.product_count)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
