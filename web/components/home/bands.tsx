import Link from "next/link";

import { CHIP_CLASSES } from "@/components/label/primitives";
import type { NutriscoreGrade, StatsOverview } from "@/lib/api";
import { HOME_WAYS_IN, MEASURED, repoFileUrl, SHELF } from "@/lib/copy";
import { additiveFinding, largestFinding, novaFinding, nutriscoreFinding } from "@/lib/findings";
import { formatCount } from "@/lib/format";

/** The dashboard's findings as one line: what the ticker scrolls. */
export function tickerFacts(stats: StatsOverview): string[] {
  return [
    `${formatCount(stats.named_product_count)} US products`,
    nutriscoreFinding(stats.nutriscore),
    novaFinding(stats.nova),
    additiveFinding(stats.top_additives),
    largestFinding(stats.categories, "category"),
    `${formatCount(stats.additive_count)} additives explained`,
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

/** The first three ways in as label panels; the rest as links. */
export function WaysIn() {
  const [tiles, rest] = [HOME_WAYS_IN.slice(0, 3), HOME_WAYS_IN.slice(3)];
  return (
    <section aria-labelledby="ways-title" className="mx-auto w-full max-w-page px-4 pt-16">
      <h2 id="ways-title" className="type-title pb-6">
        {SHELF.waysTitle}
      </h2>
      <ul className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {tiles.map((way) => (
          <li key={way.href}>
            <Link
              href={way.href}
              className="panel group/tile flex h-full flex-col justify-between gap-8 p-6 no-underline"
            >
              <span>
                <span className="type-title block">{way.title}</span>
                <span className="type-body block pt-3 text-ink-muted">{way.note}</span>
              </span>
              <span aria-hidden="true" className="type-title transition-transform group-hover/tile:translate-x-2">
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {rest.length > 0 && (
        <p className="type-body flex flex-wrap gap-x-6 gap-y-2 pt-6">
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
        <h2 id="measured-title" className="type-title">
          {SHELF.measuredTitle}
        </h2>
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
