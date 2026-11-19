"use client";

import Link from "next/link";
import { useId, useState } from "react";

import { Rule } from "@/components/label/primitives";
import { additiveHref, filterAdditives } from "@/lib/additives";
import type { AdditiveListItem, NutriscoreGrade } from "@/lib/api";
import { PREFERENCES } from "@/lib/copy";
import {
  clearPreferences,
  hasRules,
  LIMITS,
  MAX_AVOIDED,
  writePreferences,
  type AvoidedAdditive,
  type LimitKey,
  type Preferences,
} from "@/lib/preferences";
import { useHydrated, usePreferences } from "@/lib/use-preferences";

const MAX_MATCHES = 8;
const GRADE_CHOICES: NutriscoreGrade[] = ["a", "b", "c", "d"];
const INPUT = "panel type-data-value rounded-none px-3 py-2";

/** The form exists only in the browser, where the rules are kept. */
export function PreferencesForm({ additives }: { additives: AdditiveListItem[] | null }) {
  const hydrated = useHydrated();
  if (!hydrated) return <p className="type-body pt-6 text-ink-muted">Reading your rules…</p>;
  return <Form additives={additives} />;
}

/** A limit as typed, or undefined when the box is empty or holds no usable number. */
function parseLimit(text: string): number | undefined {
  if (text.trim() === "") return undefined;
  const value = Number(text.replace(",", "."));
  return Number.isFinite(value) && value >= 0 && value <= 100 ? value : undefined;
}

function Form({ additives }: { additives: AdditiveListItem[] | null }) {
  const preferences = usePreferences();
  const [drafts, setDrafts] = useState<Record<LimitKey, string>>(() => drafted(preferences));
  const save = (next: Partial<Preferences>) => writePreferences({ ...preferences, ...next });

  function setLimit(key: LimitKey, text: string) {
    setDrafts((d) => ({ ...d, [key]: text }));
    const limits = { ...preferences.limits };
    const value = parseLimit(text);
    if (value === undefined) delete limits[key];
    else limits[key] = value;
    save({ limits });
  }

  return (
    <div className="max-w-measure">
      <section aria-labelledby="limits" className="pt-8">
        <h2 id="limits" className="type-heading pb-2">
          {PREFERENCES.limitsTitle}
        </h2>
        <Rule weight="thin" />
        {LIMITS.map(({ key, name }) => (
          <LimitInput
            key={key}
            name={name}
            value={drafts[key]}
            invalid={drafts[key].trim() !== "" && parseLimit(drafts[key]) === undefined}
            onChange={(text) => setLimit(key, text)}
          />
        ))}
        <p className="type-small pt-2 text-ink-muted">{PREFERENCES.limitsNote}</p>
      </section>

      <section aria-label="Grade and processing" className="pt-8">
        <Rule weight="thin" />
        <GradeSelect
          value={preferences.minGrade}
          onChange={(minGrade) => save({ minGrade })}
        />
        <label className="type-data-label flex cursor-pointer items-center gap-3 py-3">
          <input
            type="checkbox"
            checked={preferences.avoidUltraProcessed}
            onChange={(event) => save({ avoidUltraProcessed: event.target.checked })}
            className="h-4 w-4 accent-ink"
          />
          {PREFERENCES.ultraProcessed}
        </label>
      </section>

      <AdditivesToAvoid
        additives={additives}
        avoided={preferences.avoidAdditives}
        onChange={(avoidAdditives) => save({ avoidAdditives })}
      />

      <p className="flex flex-wrap items-baseline gap-x-6 gap-y-2 pt-8">
        <span role="status" className="type-small text-ink-muted">
          {hasRules(preferences) ? PREFERENCES.saved : PREFERENCES.nothingSet}
        </span>
        {hasRules(preferences) && (
          <button
            type="button"
            className="type-small cursor-pointer underline underline-offset-2"
            onClick={() => {
              clearPreferences();
              setDrafts(drafted(null));
            }}
          >
            {PREFERENCES.clear}
          </button>
        )}
      </p>
    </div>
  );
}

function drafted(p: Preferences | null): Record<LimitKey, string> {
  return Object.fromEntries(
    LIMITS.map(({ key }) => [key, p?.limits[key]?.toString() ?? ""]),
  ) as Record<LimitKey, string>;
}

function LimitInput({
  name,
  value,
  invalid,
  onChange,
}: {
  name: string;
  value: string;
  invalid: boolean;
  onChange: (text: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule-light py-3">
      <label htmlFor={id} className="type-data-label w-[8rem]">
        {name}
      </label>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        min={0}
        max={100}
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={invalid}
        aria-describedby={invalid ? `${id}-error` : undefined}
        className={`${INPUT} w-24`}
      />
      <span className="type-data-label">{PREFERENCES.limitUnit}</span>
      {invalid && (
        <span id={`${id}-error`} className="type-small basis-full">
          A number of grams from 0 to 100. Not saved.
        </span>
      )}
    </div>
  );
}

function GradeSelect({
  value,
  onChange,
}: {
  value: NutriscoreGrade | null;
  onChange: (grade: NutriscoreGrade | null) => void;
}) {
  const id = useId();
  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-rule-light py-3">
      <label htmlFor={id} className="type-data-label w-[8rem]">
        {PREFERENCES.gradeLabel}
      </label>
      <select
        id={id}
        value={value ?? ""}
        onChange={(event) => onChange((event.target.value || null) as NutriscoreGrade | null)}
        className={`${INPUT} cursor-pointer`}
      >
        <option value="">{PREFERENCES.gradeAny}</option>
        {GRADE_CHOICES.map((grade) => (
          <option key={grade} value={grade}>
            {grade.toUpperCase()}
          </option>
        ))}
      </select>
      {value && value !== "a" && <span className="type-data-label">{PREFERENCES.gradeSuffix}</span>}
    </div>
  );
}

function AdditivesToAvoid({
  additives,
  avoided,
  onChange,
}: {
  additives: AdditiveListItem[] | null;
  avoided: AvoidedAdditive[];
  onChange: (next: AvoidedAdditive[]) => void;
}) {
  const [query, setQuery] = useState("");
  const inputId = useId();
  const ids = new Set(avoided.map((a) => a.id));
  const matches =
    additives && query.trim()
      ? filterAdditives(additives, query)
          .filter((a) => !ids.has(a.additive_id))
          .slice(0, MAX_MATCHES)
      : [];
  const full = avoided.length >= MAX_AVOIDED;

  return (
    <section aria-labelledby="avoid" className="pt-8">
      <h2 id="avoid" className="type-heading pb-2">
        {PREFERENCES.additivesTitle}
      </h2>
      <Rule weight="thin" />
      {additives === null ? (
        <p className="type-body pt-3">{PREFERENCES.additivesUnavailable}</p>
      ) : (
        <>
          <label htmlFor={inputId} className="sr-only">
            {PREFERENCES.findAdditive}
          </label>
          <input
            id={inputId}
            type="text"
            inputMode="search"
            autoComplete="off"
            spellCheck={false}
            value={query}
            disabled={full}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={PREFERENCES.findPlaceholder}
            className={`${INPUT} mt-3 block w-full`}
          />
          {matches.length > 0 && (
            <ul aria-label="Matching additives">
              {matches.map((a) => (
                <li
                  key={a.additive_id}
                  className="flex items-baseline justify-between gap-4 border-b border-rule-light py-2"
                >
                  <span className="type-data-label min-w-0">
                    {a.e_number && <span className="type-data-value pr-2">{a.e_number}</span>}
                    {a.name}
                  </span>
                  <button
                    type="button"
                    className="type-data-value shrink-0 cursor-pointer underline underline-offset-2"
                    aria-label={`${PREFERENCES.avoid} ${a.name}`}
                    onClick={() => {
                      onChange([...avoided, { id: a.additive_id, name: a.name, e_number: a.e_number }]);
                      setQuery("");
                    }}
                  >
                    {PREFERENCES.avoid}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {avoided.length === 0 ? (
        <p className="type-small pt-3 text-ink-muted">{PREFERENCES.noneAvoided}</p>
      ) : (
        <ul aria-label="Additives you avoid" className="pt-3">
          {avoided.map((a) => (
            <li
              key={a.id}
              className="flex items-baseline justify-between gap-4 border-b border-rule-light py-2"
            >
              <Link href={additiveHref(a.id)} className="type-data-label min-w-0">
                {a.e_number && <span className="type-data-value pr-2">{a.e_number}</span>}
                {a.name}
              </Link>
              <button
                type="button"
                className="type-small shrink-0 cursor-pointer underline underline-offset-2"
                aria-label={`${PREFERENCES.remove} ${a.name}`}
                onClick={() => onChange(avoided.filter((x) => x.id !== a.id))}
              >
                {PREFERENCES.remove}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
