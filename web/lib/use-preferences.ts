"use client";

/** My preferences in React, re-rendering whenever this or another tab changes them. */
import { useSyncExternalStore } from "react";

import {
  NO_PREFERENCES,
  PREFERENCES_CHANGED,
  PREFERENCES_KEY,
  readPreferences,
  type Preferences,
} from "./preferences";

// One snapshot per stored string, so components re-render only when the rules change.
let cached: { raw: string | null; value: Preferences } = { raw: null, value: NO_PREFERENCES };
function snapshot(): Preferences {
  let raw: string | null;
  try {
    raw = globalThis.localStorage?.getItem(PREFERENCES_KEY) ?? null;
  } catch {
    raw = null;
  }
  if (raw !== cached.raw) cached = { raw, value: readPreferences() };
  return cached.value;
}
function subscribe(onChange: () => void): () => void {
  globalThis.addEventListener?.(PREFERENCES_CHANGED, onChange);
  globalThis.addEventListener?.("storage", onChange); // other tabs
  return () => {
    globalThis.removeEventListener?.(PREFERENCES_CHANGED, onChange);
    globalThis.removeEventListener?.("storage", onChange);
  };
}

/** The rules; none on the server and during hydration. */
export function usePreferences(): Preferences {
  return useSyncExternalStore(subscribe, snapshot, () => NO_PREFERENCES);
}

const noop = () => () => {};
/** False on the server and during hydration, true after: for UI that only exists in the browser. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}
