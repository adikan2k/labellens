"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

import type { GraphNeighborhood } from "@/lib/api";
import { layout, readTokens, toGraph } from "@/lib/graph-view";

type Props = {
  data: GraphNeighborhood;
  selected: string;
  onSelect: (nodeId: string) => void;
};

type SigmaLike = {
  on: (event: string, handler: (payload: { node: string }) => void) => void;
  kill: () => void;
  setNodeState: (node: string, state: { isHighlighted: boolean }) => void;
  getCamera: () => { animate: (state: object, options: object) => Promise<void> };
  getNodeDisplayData: (node: string) => { x: number; y: number } | undefined;
};

// Start downloading Sigma as soon as this module loads in the browser, not after the data
// arrives, so the two overlap. (WebGL cannot run on the server.)
const sigmaModule = typeof window === "undefined" ? null : import("sigma");

function cssMs(name: string, fallback: number): number {
  const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(value) ? value : fallback;
}

/**
 * The WebGL graph. Sigma is imported in the browser only (WebGL cannot render on the server).
 * The layout is computed before the first frame, so nothing moves on its own; selecting a
 * node eases the camera to it (dur-slow), instantly under reduced motion.
 */
export function GraphCanvas({ data, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const sigma = useRef<SigmaLike | null>(null);
  const reduced = useReducedMotion();
  const select = useRef(onSelect);
  useEffect(() => {
    select.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    let cancelled = false;
    const graph = toGraph(data, readTokens());
    layout(graph, data.center);
    void (sigmaModule ?? import("sigma")).then(({ default: Sigma, DEFAULT_STYLES }) => {
      if (cancelled || !container.current) return;
      const instance = new Sigma(graph, container.current, {
        settings: {
          labelDensity: 0.6,
          labelRenderedSizeThreshold: 6,
          stagePadding: 24,
          zoomDuration: 0,
        },
        styles: {
          // Sigma's defaults, plus: labels show on hover, on the selected (highlighted) node,
          // and always on the centre product.
          nodes: [
            DEFAULT_STYLES.nodes,
            {
              labelVisibility: {
                when: (attrs, state) =>
                  state.isHovered || state.isHighlighted || attrs.isCenter === true,
                then: "visible",
                else: "auto",
              },
            },
          ],
          edges: DEFAULT_STYLES.edges,
        },
      }) as unknown as SigmaLike;
      instance.on("clickNode", ({ node }) => select.current(node));
      sigma.current = instance;
      performance.mark("graph-rendered");
    });
    return () => {
      cancelled = true;
      sigma.current?.kill();
      sigma.current = null;
    };
  }, [data]);

  const highlighted = useRef<string | null>(null);
  useEffect(() => {
    const instance = sigma.current;
    const target = instance?.getNodeDisplayData(selected);
    if (!instance || !target) return;
    if (highlighted.current && highlighted.current !== selected) {
      instance.setNodeState(highlighted.current, { isHighlighted: false });
    }
    instance.setNodeState(selected, { isHighlighted: true });
    highlighted.current = selected;
    const duration = reduced ? 0 : cssMs("--dur-slow", 420);
    void instance.getCamera().animate({ x: target.x, y: target.y }, { duration });
  }, [selected, reduced]);

  return (
    <div
      ref={container}
      data-testid="graph-canvas"
      aria-hidden="true"
      className="h-[60vh] w-full border border-rule-light"
    />
  );
}
