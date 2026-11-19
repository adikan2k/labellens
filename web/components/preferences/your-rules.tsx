"use client";

import Link from "next/link";

import { Rule } from "@/components/label/primitives";
import { PREFERENCES } from "@/lib/copy";
import { checkRules, hasRules, verdict, type Checkable } from "@/lib/preferences";
import { useHydrated, usePreferences } from "@/lib/use-preferences";

/**
 * Your rules (DESIGN.md, "My preferences"): each rule someone set, and whether this product
 * meets it, in words. With no rules, a line inviting them to set some (when `prompt`).
 */
export function YourRules({ subject, prompt = true }: { subject: Checkable; prompt?: boolean }) {
  const preferences = usePreferences();
  const hydrated = useHydrated();
  if (!hydrated) return null;
  if (!hasRules(preferences)) {
    return prompt ? (
      <p className="type-small pt-4">
        <Link href="/preferences">{PREFERENCES.prompt}</Link>
      </p>
    ) : null;
  }
  const checks = checkRules(preferences, subject);
  return (
    <section aria-labelledby="your-rules" className="mt-6 border-t border-rule-light pt-3">
      <h2 id="your-rules" className="type-heading pb-1">
        {PREFERENCES.boxTitle}
      </h2>
      <ul>
        {checks.map((check) => (
          <li key={check.key} data-outcome={check.outcome} className="border-b border-rule-light py-2">
            <span className="flex items-baseline justify-between gap-4">
              <span className="type-data-label min-w-0">{check.rule}</span>
              <span className="type-data-value shrink-0">{PREFERENCES.outcome[check.outcome]}</span>
            </span>
            {check.outcome !== "meets" && (
              <span className="type-small block text-ink-muted">{check.detail}</span>
            )}
          </li>
        ))}
      </ul>
      <p className="type-small pt-2">
        <Link href="/preferences">{PREFERENCES.edit}</Link>
      </p>
    </section>
  );
}

/** The compare table's "Your rules" row; nothing until rules are set. */
export function RulesCompareRow({ a, b }: { a: Checkable; b: Checkable }) {
  const preferences = usePreferences();
  const hydrated = useHydrated();
  if (!hydrated || !hasRules(preferences)) return null;
  return (
    <>
      <tr aria-hidden="true">
        <td colSpan={3} className="p-[0px]">
          <Rule weight="thin" />
        </td>
      </tr>
      <tr data-row="rules">
        <th scope="row" className="type-data-label py-1 text-left align-top">
          <Link href="/preferences">{PREFERENCES.compareRow}</Link>
        </th>
        {[a, b].map((subject, i) => (
          <td key={i} className="px-2 py-1 text-right align-top last:pr-[0px]">
            <span className="type-data-value">{verdict(checkRules(preferences, subject))}</span>
          </td>
        ))}
      </tr>
    </>
  );
}
