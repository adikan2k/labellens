"use client";

import { motion, useReducedMotion } from "motion/react";
import { Fragment, type ReactNode } from "react";

import { DataRow } from "@/components/label/primitives";
import type { Nutrition } from "@/lib/api";
import { missingValues } from "@/lib/copy";
import { formatEnergy, formatGrams } from "@/lib/format";
import { GROUPS, type NutritionRow } from "@/lib/nutrition";

type Row = NutritionRow;

// "The label prints" (DESIGN.md section 3). Times in seconds; the sequence ends by 0.9 s.
const EASE_OUT = [0.2, 0, 0, 1] as const;
const DUR_BASE = 0.24;
const STEP = 0.03; // rows wipe in 30 ms apart
export const PRINT_END = 0.9;

type Piece = { kind: "rule"; weight: "heavy" | "medium" | "thin" } | { kind: "row"; row: Row };

function pieces(): Piece[] {
  const out: Piece[] = [{ kind: "rule", weight: "heavy" }];
  GROUPS.forEach((group, g) => {
    group.forEach((row, r) => {
      if (r > 0) out.push({ kind: "rule", weight: "thin" });
      out.push({ kind: "row", row });
    });
    out.push({ kind: "rule", weight: g === GROUPS.length - 1 ? "heavy" : "medium" });
  });
  return out;
}

export const PIECES = pieces();

/** Seconds after mount at which piece `index` starts: the top rule first, then one step each. */
export function startOf(index: number): number {
  return index === 0 ? 0 : DUR_BASE / 2 + (index - 1) * STEP;
}

function Animated({ index, kind, children }: { index: number; kind: Piece["kind"]; children: ReactNode }) {
  const transition = { duration: DUR_BASE, ease: EASE_OUT, delay: startOf(index) };
  if (kind === "rule") {
    return (
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={transition}
        style={{ transformOrigin: "left" }}
      >
        {children}
      </motion.div>
    );
  }
  return (
    <motion.div
      initial={{ clipPath: "inset(0 100% 0 0)" }}
      animate={{ clipPath: "inset(0 0% 0 0)" }}
      transition={transition}
    >
      {children}
    </motion.div>
  );
}

/** The Nutrition Facts panel. Prints once on mount; complete and still under reduced motion. */
export function NutritionPanel({ nutrition }: { nutrition: Nutrition }) {
  const reduced = useReducedMotion();
  const missing = GROUPS.flat()
    .filter((row) => nutrition[row.key] === null)
    .map((row) => row.noun);
  const footnote = missingValues(missing);

  return (
    <section aria-labelledby="nutrition-title" className="panel px-4 pt-3 pb-4" data-print={reduced ? "static" : "animated"}>
      <h2 id="nutrition-title" className="type-title">
        Nutrition Facts
      </h2>
      <p className="type-small pb-2">Per 100 g</p>
      {PIECES.map((piece, index) => {
        const content =
          piece.kind === "rule" ? (
            <div aria-hidden="true" className={`rule-${piece.weight}`} />
          ) : (
            <Value row={piece.row} value={nutrition[piece.row.key]} />
          );
        return (
          <Fragment key={index}>
            {reduced ? content : <Animated index={index} kind={piece.kind}>{content}</Animated>}
          </Fragment>
        );
      })}
      {footnote && <p className="type-small pt-3 text-ink-muted">{footnote}</p>}
    </section>
  );
}

function Value({ row, value }: { row: Row; value: number | null }) {
  if (value === null) return <DataRow label={row.label} indent={row.indent} missing />;
  const text = row.key === "energy_kcal_100g" ? formatEnergy(value) : formatGrams(value);
  return <DataRow label={row.label} value={text} indent={row.indent} />;
}
