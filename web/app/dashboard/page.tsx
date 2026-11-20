import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";

import { BarChart, DataTable, GradeStacks } from "@/components/dashboard/charts";
import { Rule } from "@/components/label/primitives";
import type { NutriscoreGrade, StatsOverview } from "@/lib/api";
import { cachedStats } from "@/lib/cached";
import { WAKING_UP } from "@/lib/copy";
import {
  additiveFinding,
  categorySourceNote,
  largestFinding,
  novaFinding,
  nutriscoreFinding,
  poorGradeFinding,
  poorGradeShares,
  sugarFinding,
} from "@/lib/findings";
import { formatCount, formatShare } from "@/lib/format";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <div className="mx-auto w-full max-w-page px-4 pt-8 pb-16">
      <h1 className="type-title">The US label landscape</h1>
      <Suspense fallback={<p className="type-body pt-4 text-ink-muted">Counting products…</p>}>
        <Dashboard />
      </Suspense>
    </div>
  );
}

async function Dashboard() {
  let stats: StatsOverview;
  try {
    stats = await cachedStats();
  } catch {
    return <p className="type-body pt-4">{WAKING_UP}</p>;
  }
  const graded = stats.nutriscore.filter((r) => r.key);
  const gradedTotal = graded.reduce((s, r) => s + r.count, 0);
  const nova = stats.nova.filter((r) => r.key);
  const novaTotal = nova.reduce((s, r) => s + r.count, 0);
  const categories = [...stats.categories].sort((a, b) => b.count - a.count).slice(0, 10);
  const poor = poorGradeShares(stats);

  return (
    <>
      <p className="type-body max-w-measure pt-3 text-ink-muted">
        {formatCount(stats.product_count)} products sold in the US, from the Open Food Facts snapshot of{" "}
        {stats.source.snapshot_date ?? "unknown date"}.{" "}
        {stats.named_product_count < stats.product_count &&
          `${formatCount(stats.named_product_count)} of them have a name and can be searched; the charts count them all.`}
      </p>
      <div className="grid gap-x-12 gap-y-16 pt-12 lg:grid-cols-2">
        <ChartPanel id="nutriscore" finding={nutriscoreFinding(stats.nutriscore)}>
          <BarChart
            bars={graded.map((r) => ({
              label: `Nutri-Score ${r.key!.toUpperCase()}`,
              value: r.count,
              display: formatShare(r.count, gradedTotal),
              grade: r.key as NutriscoreGrade,
            }))}
          />
          <Note>
            {formatCount(stats.product_count - gradedTotal)} products have no Nutri-Score and are not shown.
          </Note>
          <DataTable
            caption="Products per Nutri-Score grade"
            headers={["Grade", "Products", "Share of graded"]}
            rows={graded.map((r) => [r.key!.toUpperCase(), formatCount(r.count), formatShare(r.count, gradedTotal)])}
          />
        </ChartPanel>

        <ChartPanel id="nova" finding={novaFinding(stats.nova)}>
          <BarChart
            bars={nova.map((r) => ({
              label: `NOVA ${r.key}`,
              value: r.count,
              display: formatShare(r.count, novaTotal),
            }))}
          />
          <Note>NOVA 1 is unprocessed or minimally processed; NOVA 4 is ultra-processed.</Note>
          <DataTable
            caption="Products per NOVA group"
            headers={["Group", "Products", "Share"]}
            rows={nova.map((r) => [`${r.key}: ${r.label}`, formatCount(r.count), formatShare(r.count, novaTotal)])}
          />
        </ChartPanel>

        <ChartPanel id="categories" finding={largestFinding(categories, "category")}>
          <BarChart bars={categories.map((r) => ({ label: r.label, value: r.count, display: formatCount(r.count) }))} />
          <Note>{categorySourceNote(stats.category_sources)}</Note>
          <DataTable
            caption="Products per category"
            headers={["Category", "Products"]}
            rows={stats.categories.map((r) => [r.label, formatCount(r.count)])}
          />
        </ChartPanel>

        <ChartPanel id="additives" finding={additiveFinding(stats.top_additives)}>
          <BarChart
            bars={stats.top_additives.slice(0, 10).map((r) => ({ label: r.label, value: r.count, display: formatCount(r.count) }))}
          />
          <DataTable
            caption="Most common additives"
            headers={["Additive", "Products"]}
            rows={stats.top_additives.map((r) => [r.label, formatCount(r.count)])}
          />
        </ChartPanel>

        <ChartPanel id="grades-by-category" finding={poorGradeFinding(stats)}>
          <GradeStacks
            stacks={stats.nutriscore_by_category
              .slice()
              .sort((a, b) => (b.grades.d + b.grades.e) / b.graded_count - (a.grades.d + a.grades.e) / a.graded_count)
              .slice(0, 10)
              .map((c) => ({ label: c.name, parts: c.grades, total: c.graded_count }))}
          />
          <Note>Graded products only; categories with at least 200 of them.</Note>
          <DataTable
            caption="Share of graded products scoring D or E, per category"
            headers={["Category", "Graded", "D or E"]}
            rows={poor.map((c) => [c.name, formatCount(c.graded), `${Math.round(c.share * 100)}%`])}
          />
        </ChartPanel>

        <ChartPanel id="sugar" finding={sugarFinding(stats)}>
          <BarChart
            bars={[...stats.median_sugars_by_category]
              .sort((a, b) => b.median - a.median)
              .slice(0, 10)
              .map((c) => ({ label: c.name, value: c.median, display: `${c.median} g` }))}
          />
          <Note>Median sugars per 100 g, among products in the category that list sugar.</Note>
          <DataTable
            caption="Median sugars per 100 g, per category"
            headers={["Category", "Products", "Median"]}
            rows={[...stats.median_sugars_by_category]
              .sort((a, b) => b.median - a.median)
              .map((c) => [c.name, formatCount(c.product_count), `${c.median} g`])}
          />
        </ChartPanel>
      </div>
    </>
  );
}

function ChartPanel({ id, finding, children }: { id: string; finding: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-finding`} className="min-w-0 scroll-mt-8">
      <Rule weight="heavy" />
      <h2 id={`${id}-finding`} className="type-heading pt-3 pb-4">
        {finding}
      </h2>
      {children}
    </section>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="type-small pt-3 text-ink-muted">{children}</p>;
}
