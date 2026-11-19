"use client";

/** My basket in React: the barcodes, re-rendering whenever this or another tab changes them. */
import { useSyncExternalStore } from "react";

import { BASKET_KEY, CHANGED, readBasket } from "./basket";

// One snapshot string, so components re-render only when the basket changes.
let cached = { raw: "", codes: [] as string[] };
function snapshot(): string[] {
  const raw = (() => {
    try {
      return globalThis.localStorage?.getItem(BASKET_KEY) ?? "[]";
    } catch {
      return "[]";
    }
  })();
  if (raw !== cached.raw) cached = { raw, codes: readBasket() };
  return cached.codes;
}
const EMPTY: string[] = [];
function subscribe(onChange: () => void): () => void {
  globalThis.addEventListener?.(CHANGED, onChange);
  globalThis.addEventListener?.("storage", onChange); // other tabs
  return () => {
    globalThis.removeEventListener?.(CHANGED, onChange);
    globalThis.removeEventListener?.("storage", onChange);
  };
}

/** The basket's barcodes; empty on the server and during hydration. */
export function useBasket(): string[] {
  return useSyncExternalStore(subscribe, snapshot, () => EMPTY);
}

