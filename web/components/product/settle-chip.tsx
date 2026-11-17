"use client";

import { motion, useReducedMotion } from "motion/react";
import { ViewTransition } from "react";

import { GradeChip } from "@/components/label/primitives";
import type { NutriscoreGrade } from "@/lib/api";

// The last beat of the label print: the chip settles from 1.06 to 1 over dur-slow.
const SETTLE_DELAY = 0.45;
const DUR_SLOW = 0.42;

export function SettleChip({ code, grade }: { code: string; grade: NutriscoreGrade | null }) {
  const reduced = useReducedMotion();
  const chip = <GradeChip grade={grade} size="lg" />;
  return (
    <ViewTransition name={`grade-${code}`} share="morph" default="none">
      {reduced || !grade ? (
        <span className="inline-block">{chip}</span>
      ) : (
        <motion.span
          className="inline-block"
          initial={{ scale: 1.06 }}
          animate={{ scale: 1 }}
          transition={{ duration: DUR_SLOW, ease: [0.2, 0, 0, 1], delay: SETTLE_DELAY }}
        >
          {chip}
        </motion.span>
      )}
    </ViewTransition>
  );
}
