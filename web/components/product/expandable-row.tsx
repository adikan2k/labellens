"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type ReactNode, useId, useState } from "react";

import type { Explainer } from "@/lib/api";
import { AI_NOTE } from "@/lib/copy";

/** A row that expands to show more (height animation, dur-base); still under reduced motion. */
export function ExpandableRow({ label, children }: { label: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const reduced = useReducedMotion();
  const panelId = useId();

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full cursor-pointer items-baseline justify-between gap-4 py-2 text-left"
      >
        {label}
        <span aria-hidden="true" className={`type-small ${open ? "rotate-180" : ""}`}>
          ⌄
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={panelId}
            key="detail"
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={reduced ? undefined : { height: 0, opacity: 0 }}
            transition={{ duration: reduced ? 0 : 0.24, ease: [0.2, 0, 0, 1] }}
            className="overflow-hidden"
          >
            <div className="type-body max-w-measure pb-3">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

/** An explainer's text, with the AI note when a model wrote it. */
export function ExplainerText({ explainer }: { explainer: NonNullable<Explainer> }) {
  return (
    <>
      <p>{explainer.text}</p>
      {explainer.ai_generated && <p className="type-small pt-1 text-ink-muted">{AI_NOTE}</p>}
    </>
  );
}
