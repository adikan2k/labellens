"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useId, useState } from "react";

import type { Additive } from "@/lib/api";
import { AI_NOTE } from "@/lib/copy";

/** Additives as rows that expand to show what each does (height animation, dur-base). */
export function AdditiveList({ additives }: { additives: Additive[] }) {
  return (
    <ul>
      {additives.map((additive) => (
        <li key={additive.additive_id} className="border-b border-rule-light">
          <AdditiveRow additive={additive} />
        </li>
      ))}
    </ul>
  );
}

function AdditiveRow({ additive }: { additive: Additive }) {
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
        <span className="type-data-label">
          {additive.e_number && <span className="type-data-value pr-2">{additive.e_number}</span>}
          {additive.name}
        </span>
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
            <div className="type-body max-w-measure pb-3">
              {additive.explainer ? (
                <>
                  <p>{additive.explainer.text}</p>
                  {additive.explainer.ai_generated && (
                    <p className="type-small pt-1 text-ink-muted">{AI_NOTE}</p>
                  )}
                </>
              ) : (
                <p>
                  {additive.function
                    ? `Used as: ${additive.function.toLowerCase()}.`
                    : "Open Food Facts does not list what it is used for."}
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
