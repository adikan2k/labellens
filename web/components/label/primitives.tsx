import type { ComponentPropsWithoutRef, ReactNode } from "react";

import type { NutriscoreGrade } from "@/lib/api";

/** A heavy, medium or thin rule: structure between groups, never decoration (DESIGN.md). */
export function Rule({
  weight,
  className = "",
}: {
  weight: "heavy" | "medium" | "thin" | "hair";
  className?: string;
}) {
  return <div aria-hidden="true" data-rule={weight} className={`rule-${weight} ${className}`} />;
}

/** The one panel style: 2 px ink border, square corners, paper background. */
export function Panel({ children, className = "", ...rest }: ComponentPropsWithoutRef<"section">) {
  return (
    <section className={`panel px-4 py-2 ${className}`} {...rest}>
      {children}
    </section>
  );
}

/** One label row: name on the left, value right-aligned in tabular figures. */
export function DataRow({
  label,
  value,
  indent = false,
  missing = false,
  className = "",
}: {
  label: ReactNode;
  value?: ReactNode;
  indent?: boolean;
  missing?: boolean;
  className?: string;
}) {
  return (
    <div data-row className={`flex items-baseline justify-between gap-4 py-1 ${className}`}>
      <span className={`type-data-label ${indent ? "pl-4" : ""}`}>{label}</span>
      {missing ? (
        <span className="type-data-label text-right text-ink-muted">Not listed</span>
      ) : (
        <span className="type-data-value text-right">{value}</span>
      )}
    </div>
  );
}

// Text colour per grade, checked against WCAG AA in grade-chip.test.tsx (see DESIGN.md).
const CHIP: Record<NutriscoreGrade, string> = {
  a: "bg-grade-a text-paper",
  b: "bg-grade-b text-ink",
  c: "bg-grade-c text-ink",
  d: "bg-grade-d text-ink",
  e: "bg-grade-e text-ink",
};

/** Nutri-Score chip. The letter is always present; colour is never the only signal. */
export function GradeChip({
  grade,
  size = "md",
}: {
  grade: NutriscoreGrade | null | undefined;
  size?: "md" | "lg";
}) {
  if (!grade) {
    return <span className="type-small text-ink-muted">No Nutri-Score</span>;
  }
  const box = size === "lg" ? "h-12 w-12 type-heading" : "h-8 w-8 type-data-value";
  return (
    <span
      role="img"
      aria-label={`Nutri-Score ${grade.toUpperCase()}`}
      data-grade={grade}
      className={`inline-flex shrink-0 items-center justify-center rounded-control ${box} ${CHIP[grade]}`}
    >
      <span aria-hidden="true">{grade.toUpperCase()}</span>
    </span>
  );
}

export const CHIP_CLASSES = CHIP;
