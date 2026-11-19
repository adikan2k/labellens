"use client";

import { useState } from "react";

import { SHELF } from "@/lib/copy";

/**
 * An ink band of facts, scrolling slowly (DESIGN.md, Home). It pauses on hover and with its
 * own button (moving text needs a way to stop it), and stands still under reduced motion.
 * The second copy, which makes the loop seamless, is hidden from screen readers.
 */
export function Ticker({ facts }: { facts: string[] }) {
  const [paused, setPaused] = useState(false);
  const line = (hidden: boolean) => (
    <ul aria-hidden={hidden || undefined} className="flex shrink-0 items-baseline">
      {facts.map((fact) => (
        <li key={fact} className="type-data-value flex shrink-0 items-baseline whitespace-nowrap">
          <span className="px-6">{fact}</span>
          <span aria-hidden="true" className="text-paper-muted">
            ·
          </span>
        </li>
      ))}
    </ul>
  );
  return (
    <section aria-label={SHELF.tickerLabel} className="band-ink flex items-center">
      <div className="min-w-0 flex-1 overflow-hidden py-4">
        <div
          data-paused={paused || undefined}
          className="animate-ticker flex w-max data-[paused]:[animation-play-state:paused]"
        >
          {line(false)}
          {line(true)}
        </div>
      </div>
      <button
        type="button"
        aria-pressed={paused}
        onClick={() => setPaused((p) => !p)}
        className="type-small shrink-0 cursor-pointer border-l border-paper-muted px-4 py-4 underline underline-offset-2"
      >
        {paused ? SHELF.play : SHELF.pause}
      </button>
    </section>
  );
}
