"use client";

import { motion, useInView, useReducedMotion } from "motion/react";
import { type CSSProperties, type ReactNode, useRef } from "react";

/** dur-slow and ease-out from DESIGN.md. */
const SLOW = 0.42;
const EASE_OUT = [0.2, 0, 0, 1] as const;

/**
 * Wipes in from the left once, the first time it scrolls into view: the label's print move,
 * as a clip-path, so the text inside is never stretched and nothing shifts. Still under
 * reduced motion.
 */
export function WipeIn({ children, className }: { children: ReactNode; className: string }) {
  const reduced = useReducedMotion();
  // The wrapper is what is watched: the browser counts a fully clipped element as not visible,
  // so watching the wiped element itself would never start the wipe.
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  if (reduced) {
    return (
      <div data-reveal="still" className={className}>
        {children}
      </div>
    );
  }
  return (
    <div ref={ref} className={className}>
      <motion.div
        data-reveal="wipe"
        initial={{ clipPath: "inset(0 100% 0 0)" }}
        animate={inView ? { clipPath: "inset(0 0% 0 0)" } : undefined}
        transition={{ duration: SLOW, ease: EASE_OUT }}
      >
        {children}
      </motion.div>
    </div>
  );
}

/** A bar that grows from the left once, in view (transform only); still under reduced motion. */
export function GrowBar({
  className,
  style,
  order = 0,
}: {
  className: string;
  style: CSSProperties;
  order?: number;
}) {
  const reduced = useReducedMotion();
  if (reduced) {
    return <span aria-hidden="true" data-reveal="still" className={className} style={style} />;
  }
  return (
    <motion.span
      aria-hidden="true"
      data-reveal="grow"
      className={className}
      style={{ ...style, transformOrigin: "left" }}
      initial={{ scaleX: 0 }}
      whileInView={{ scaleX: 1 }}
      viewport={{ once: true, amount: 0.6 }}
      transition={{ duration: SLOW, ease: EASE_OUT, delay: order * 0.06 }}
    />
  );
}
