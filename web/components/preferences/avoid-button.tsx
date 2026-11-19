"use client";

import Link from "next/link";

import { writePreferences, type AvoidedAdditive } from "@/lib/preferences";
import { useHydrated, usePreferences } from "@/lib/use-preferences";

/** On an additive's guide page: add it to the additives you avoid, or say it's already there. */
export function AvoidButton({ additive }: { additive: AvoidedAdditive }) {
  const preferences = usePreferences();
  const hydrated = useHydrated();
  if (!hydrated) return null;
  const avoided = preferences.avoidAdditives.some((a) => a.id === additive.id);
  if (avoided) {
    return (
      <Link href="/preferences" className="type-data-value">
        In the additives you avoid
      </Link>
    );
  }
  return (
    <button
      type="button"
      className="type-data-value cursor-pointer underline underline-offset-2"
      onClick={() =>
        writePreferences({
          ...preferences,
          avoidAdditives: [...preferences.avoidAdditives, additive],
        })
      }
    >
      Add to the additives I avoid
    </button>
  );
}
