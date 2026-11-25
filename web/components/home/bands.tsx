import Link from "next/link";

import { CHIP_CLASSES } from "@/components/label/primitives";
import type { NutriscoreGrade, StatsOverview } from "@/lib/api";
import { Rule } from "@/components/label/primitives";
import { BUILT_HREF, BUILT_LABEL, HOME_INTRO, HOME_WAYS_IN, MEASURED, repoFileUrl, SHELF } from "@/lib/copy";
import { additiveFinding, largestFinding, novaFinding, nutriscoreFinding } from "@/lib/findings";
import { formatCount } from "@/lib/format";

/**
 * The dashboard's findings as one line: what the ticker scrolls. `guideCount` is how many
 * additives the additive guide lists (those a product lists), so the two pages agree; the
 * fact is left out when it is unknown. (stats.additive_count is every additive in the
 * taxonomy, a larger number that no page shows.)
 */
export function tickerFacts(stats: StatsOverview, guideCount: number | null = null): string[] {
  return [
    `${formatCount(stats.named_product_count)} US products`,
    nutriscoreFinding(stats.nutriscore),
    novaFinding(stats.nova),
    additiveFinding(stats.top_additives),
    largestFinding(stats.categories, "category"),
    ...(guideCount ? [`${formatCount(guideCount)} additives in the additive guide`] : []),
  ];
}

export type GradeShare = { grade: NutriscoreGrade; count: number; share: number };

/** Graded products by grade, A to E, with each one's share of all graded products. */
export function gradeShares(stats: StatsOverview): GradeShare[] {
  const grades: NutriscoreGrade[] = ["a", "b", "c", "d", "e"];
  const counts = grades.map((g) => stats.nutriscore.find((row) => row.key === g)?.count ?? 0);
  const total = counts.reduce((sum, n) => sum + n, 0);
  return grades.map((grade, i) => ({
    grade,
    count: counts[i],
    share: total ? counts[i] / total : 0,
  }));
}

function percent(share: number): string {
  const p = Math.round(share * 100);
  return share > 0 && p === 0 ? "<1%" : `${p}%`;
}

/** The shelf, graded: every graded US product, as the five Nutri-Score colours. */
export function GradeStrip({ stats }: { stats: StatsOverview }) {
  const shares = gradeShares(stats);
  const total = shares.reduce((sum, s) => sum + s.count, 0);
  if (total === 0) return null;
  const largest = Math.max(...shares.map((s) => s.share));
  return (
    <section aria-labelledby="shelf-title" className="mx-auto w-full max-w-page px-4 pt-16">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 pb-4">
        <h2 id="shelf-title" className="type-title">
          {SHELF.title}
        </h2>
        <Link href="/dashboard#nutriscore" className="type-data-value">
          {SHELF.link}
        </Link>
      </div>
      <p className="type-body max-w-measure pb-6 text-ink-muted">
        {SHELF.caption(formatCount(total))}
      </p>

      {/* Wide screens: one strip, each grade as wide as its share. */}
      <ol aria-label={SHELF.listLabel} className="hidden h-[16rem] sm:flex">
        {shares.map(({ grade, count, share }) => (
          <li
            key={grade}
            data-grade={grade}
            style={{ flexGrow: count, flexBasis: 0 }}
            className={`flex min-w-16 flex-col justify-between p-3 ${CHIP_CLASSES[grade]}`}
          >
            <span className="type-display" aria-hidden="true">
              {grade.toUpperCase()}
            </span>
            <span>
              <span className="sr-only">Nutri-Score {grade.toUpperCase()}: </span>
              <span className="type-title block">{percent(share)}</span>
              <span className="type-small block">{formatCount(count)}</span>
            </span>
          </li>
        ))}
      </ol>

      {/* Phones: a row per grade, its bar as long as its share. */}
      <ol aria-label={SHELF.listLabel} className="sm:hidden">
        {shares.map(({ grade, count, share }) => (
          <li key={grade} className="flex items-center gap-3 py-1">
            <span
              aria-hidden="true"
              className={`type-heading flex h-12 w-12 shrink-0 items-center justify-center ${CHIP_CLASSES[grade]}`}
            >
              {grade.toUpperCase()}
            </span>
            <span className="h-12 min-w-0 flex-1">
              <span
                aria-hidden="true"
                className={`block h-full ${CHIP_CLASSES[grade]}`}
                style={{ width: `${Math.max(2, (share / largest) * 100)}%` }}
              />
            </span>
            <span className="w-24 shrink-0 text-right">
              <span className="sr-only">Nutri-Score {grade.toUpperCase()}: </span>
              <span className="type-data-value block">{percent(share)}</span>
              <span className="type-small block text-ink-muted">{formatCount(count)}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** What LabelLens is, above the search: the hero says it before a visitor has to guess. */
export function Intro() {
  return (
    <div className="pb-8">
      <p className="type-title">{HOME_INTRO.title}</p>
      <p className="type-body max-w-measure pt-3 text-ink-muted">{HOME_INTRO.body}</p>
    </div>
  );
}

/** The first three ways in, beside the label: one label panel, a row each. */
export function StartHere() {
  return (
    <nav aria-labelledby="start-title" className="pt-6">
      <h2 id="start-title" className="type-data-label pb-2">
        {HOME_INTRO.start}
      </h2>
      <div className="panel px-4 pt-3 pb-1">
        <Rule weight="heavy" />
        <ul>
          {HOME_WAYS_IN.slice(0, 3).map((way) => (
            <li key={way.href} className="border-b border-rule-light last:border-b-0">
              <Link
                href={way.href}
                className="group/row flex items-center justify-between gap-6 py-4 no-underline"
              >
                <span>
                  <span className="type-heading block">{way.title}</span>
                  <span className="type-small block pt-1 text-ink-muted">{way.note}</span>
                </span>
                <span
                  aria-hidden="true"
                  className="type-heading transition-transform group-hover/row:translate-x-2"
                >
                  →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}

/** The rest of the ways in, as links; the first three are beside the label (StartHere). */
export function WaysIn() {
  const rest = HOME_WAYS_IN.slice(3);
  return (
    <section aria-labelledby="ways-title" className="mx-auto w-full max-w-page px-4 pt-16">
      <h2 id="ways-title" className="type-title pb-2">
        {SHELF.waysTitle}
      </h2>
      {rest.length > 0 && (
        <p className="type-body flex flex-wrap gap-x-6 gap-y-2 pt-4">
          {rest.map((way) => (
            <Link key={way.href} href={way.href} className="type-data-value">
              {way.title}
            </Link>
          ))}
        </p>
      )}
    </section>
  );
}

/** How it's measured: four numbers from the evals, each linked to its report. */
export function Measured() {
  return (
    <section aria-labelledby="measured-title" className="band-ink mt-16 -mb-16 py-16">
      {/* Runs straight into the footer band: one black block, with the footer's hairline. */}
      <div className="mx-auto w-full max-w-page px-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <h2 id="measured-title" className="type-title">
            {SHELF.measuredTitle}
          </h2>
          <Link href={BUILT_HREF} className="type-data-value">
            {BUILT_LABEL}
          </Link>
        </div>
        <p className="type-body max-w-measure pt-3 text-paper-muted">{SHELF.measuredCaption}</p>
        <ul className="grid grid-cols-1 gap-x-8 gap-y-12 pt-12 sm:grid-cols-2 lg:grid-cols-4">
          {MEASURED.map((m) => (
            <li key={m.file}>
              <span className="type-display block">{m.value}</span>
              <span className="type-body block pt-2">{m.label}</span>
              <a href={repoFileUrl(m.file)} className="type-small inline-block pt-2">
                {SHELF.report}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
