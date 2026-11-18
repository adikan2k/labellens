"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import type { NutriscoreGrade } from "@/lib/api";

const GRADE_BG: Record<NutriscoreGrade, string> = {
  a: "bg-grade-a",
  b: "bg-grade-b",
  c: "bg-grade-c",
  d: "bg-grade-d",
  e: "bg-grade-e",
};

/** Grows from zero once, the first time it scrolls into view; still under reduced motion. */
function Grow({
  children,
  className,
  width = "100%",
}: {
  children?: ReactNode;
  className: string;
  width?: string;
}) {
  const reduced = useReducedMotion();
  if (reduced) {
    return (
      <div data-bar className={className} style={{ width }}>
        {children}
      </div>
    );
  }
  return (
    <motion.div
      data-bar
      className={className}
      style={{ width, transformOrigin: "left" }}
      initial={{ scaleX: 0 }}
      whileInView={{ scaleX: 1 }}
      viewport={{ once: true, amount: 0.6 }}
      transition={{ duration: 0.42, ease: [0.2, 0, 0, 1] }}
    >
      {children}
    </motion.div>
  );
}

export type Bar = {
  label: string;
  value: number;
  display: string;
  /** Only for Nutri-Score data: colours the bar and shows the letter. */
  grade?: NutriscoreGrade;
};

/** Horizontal bars: label, bar, value right-aligned in tabular figures. */
export function BarChart({ bars }: { bars: Bar[] }) {
  const max = Math.max(...bars.map((b) => b.value), 1);
  return (
    <ul aria-hidden="true" className="space-y-2">
      {bars.map((bar) => (
        <li key={bar.label} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_auto] items-center gap-3">
          <span className="type-data-label break-words">{bar.label}</span>
          <span className="block h-4">
            <Grow
              className={`h-4 ${bar.grade ? GRADE_BG[bar.grade] : "bg-ink"}`}
              width={`${(100 * bar.value) / max}%`}
            />
          </span>
          <span className="type-data-value text-right">{bar.display}</span>
        </li>
      ))}
    </ul>
  );
}

export type Stack = { label: string; parts: Record<NutriscoreGrade, number>; total: number };

/** One stacked bar per row, split by Nutri-Score grade, with a lettered legend. */
export function GradeStacks({ stacks }: { stacks: Stack[] }) {
  const grades: NutriscoreGrade[] = ["a", "b", "c", "d", "e"];
  return (
    <div aria-hidden="true">
      <ul className="flex gap-3 pb-3">
        {grades.map((g) => (
          <li key={g} className="type-small flex items-center gap-1">
            <span className={`inline-block h-3 w-3 rounded-control ${GRADE_BG[g]}`} />
            {g.toUpperCase()}
          </li>
        ))}
      </ul>
      <ul className="space-y-2">
        {stacks.map((stack) => (
          <li key={stack.label} className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)] items-center gap-3">
            <span className="type-data-label break-words">{stack.label}</span>
            <Grow className="flex h-4">
              {grades.map((g) =>
                stack.parts[g] ? (
                  <span
                    key={g}
                    className={`block h-4 ${GRADE_BG[g]}`}
                    style={{ width: `${(100 * stack.parts[g]) / stack.total}%` }}
                  />
                ) : null,
              )}
            </Grow>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The chart's data as a table, on request (DESIGN.md quality floor), in the data row roles. */
export function DataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: (string | number)[][] }) {
  return (
    <details className="pt-4">
      <summary className="type-small cursor-pointer underline underline-offset-2">Show the numbers</summary>
      <table className="mt-3 w-full">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-ink">
            {headers.map((h, i) => (
              <th key={h} scope="col" className={`type-data-label py-1 ${i ? "text-right" : "text-left"}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row[0])} className="border-b border-rule-light">
              {row.map((cell, i) =>
                i === 0 ? (
                  <th key={i} scope="row" className="type-data-label py-1 text-left">
                    {cell}
                  </th>
                ) : (
                  <td key={i} className="type-data-value py-1 text-right">
                    {cell}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
