"use client";

import type Graph from "graphology";
import { useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

import type { GraphNeighborhood } from "@/lib/api";
import {
  type LabelBox,
  labelPriority,
  layout,
  type NodeAttributes,
  pickLabels,
  readTokens,
  toGraph,
} from "@/lib/graph-view";

type Props = {
  data: GraphNeighborhood;
  selected: string;
  onSelect: (nodeId: string) => void;
};

type Point = { x: number; y: number };

type SigmaLike = {
  on: (event: string, handler: (payload: { node: string }) => void) => void;
  kill: () => void;
  setNodeState: (node: string, state: { isHighlighted: boolean }) => void;
  getCamera: () => {
    animate: (state: object, options: object) => Promise<void>;
    on: (event: "updated", handler: () => void) => void;
  };
  getNodeDisplayData: (node: string) => (Point & { size: number }) | undefined;
  framedGraphToViewport: (point: Point) => Point;
  scaleSize: (size: number) => number;
};

// Sigma's node labels: 12 px sans-serif, drawn to the right of the dot.
const LABEL_FONT = "12px sans-serif";
const LABEL_HEIGHT = 16;
const LABEL_GAP = 4;

// Start downloading Sigma as soon as this module loads in the browser, not after the data
// arrives, so the two overlap. (WebGL cannot run on the server.)
const sigmaModule = typeof window === "undefined" ? null : import("sigma");
const shapesModule = typeof window === "undefined" ? null : import("sigma/rendering");

function cssMs(name: string, fallback: number): number {
  const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(value) ? value : fallback;
}

/** Text width in pixels, measured once per label. */
function labelMeasurer(): (text: string) => number {
  const context = document.createElement("canvas").getContext("2d");
  const widths = new Map<string, number>();
  return (text) => {
    let width = widths.get(text);
    if (width === undefined) {
      if (context) context.font = LABEL_FONT;
      width = context ? context.measureText(text).width : text.length * 7;
      widths.set(text, width);
    }
    return width;
  };
}

/** Shows the labels that fit without overlapping at the current camera, hides the rest. */
function relabel(
  instance: SigmaLike,
  graph: Graph<NodeAttributes>,
  forced: string[],
  measure: (text: string) => number,
  bounds: { width: number; height: number },
): void {
  const dots: LabelBox[] = [];
  const boxes: LabelBox[] = [];
  graph.forEachNode((id, attrs) => {
    const display = instance.getNodeDisplayData(id);
    if (!display) return;
    const at = instance.framedGraphToViewport(display);
    const radius = instance.scaleSize(display.size);
    dots.push({ id, left: at.x - radius, top: at.y - radius, width: 2 * radius, height: 2 * radius });
    boxes.push({
      id,
      left: at.x + radius + LABEL_GAP,
      top: at.y - LABEL_HEIGHT / 2,
      width: measure(attrs.label),
      height: LABEL_HEIGHT,
    });
  });
  const priority = (id: string) =>
    labelPriority(graph.getNodeAttribute(id, "kind"), graph.degree(id));
  const shown = pickLabels(boxes, forced, priority, { dots, bounds });
  graph.updateEachNodeAttributes((id, attrs) =>
    attrs.labelShown === shown.has(id) ? attrs : { ...attrs, labelShown: shown.has(id) },
  );
}

/**
 * The WebGL graph. Sigma is imported in the browser only (WebGL cannot render on the server).
 * The layout is computed before the first frame, so nothing moves on its own; selecting a
 * node eases the camera to it (dur-slow), instantly under reduced motion. Labels are chosen
 * so that none overlap, again after every camera move.
 */
export function GraphCanvas({ data, selected, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const sigma = useRef<SigmaLike | null>(null);
  const relabelNow = useRef<(selected: string) => void>(() => {});
  const reduced = useReducedMotion();
  const select = useRef(onSelect);
  const latestSelected = useRef(selected);
  useEffect(() => {
    select.current = onSelect;
    latestSelected.current = selected;
  }, [onSelect, selected]);

  useEffect(() => {
    let cancelled = false;
    const graph = toGraph(data, readTokens());
    layout(graph, data.center);
    void Promise.all([
      sigmaModule ?? import("sigma"),
      shapesModule ?? import("sigma/rendering"),
    ]).then(([{ default: Sigma, DEFAULT_STYLES }, shapes]) => {
      if (cancelled || !container.current) return;
      const instance = new Sigma(graph, container.current, {
        // One shape per kind of node (KIND_SHAPE in graph-view); the names are Sigma's own.
        primitives: {
          nodes: {
            shapes: [
              shapes.sdfCircle(),
              shapes.sdfSquare(),
              shapes.sdfDiamond(),
              shapes.sdfTriangle(),
            ],
          },
        },
        settings: {
          stagePadding: 24,
          zoomDuration: 0,
        },
        styles: {
          // Sigma's defaults, plus: a label shows when it fits without overlapping another
          // (labelShown, from pickLabels), on hover, and on the selected (highlighted) node.
          nodes: [
            DEFAULT_STYLES.nodes,
            {
              shape: { attribute: "shape", defaultValue: "circle" },
              labelVisibility: {
                when: (attrs, state) =>
                  state.isHovered || state.isHighlighted || attrs.labelShown === true,
                then: "visible",
                else: "hidden",
              },
            },
          ],
          edges: DEFAULT_STYLES.edges,
        },
      }) as unknown as SigmaLike;
      instance.on("clickNode", ({ node }) => select.current(node));
      const measure = labelMeasurer();
      const box = container.current;
      relabelNow.current = (chosen) =>
        relabel(instance, graph, [data.center, chosen], measure, {
          width: box.clientWidth,
          height: box.clientHeight,
        });
      // One relabel per frame while the camera moves (a zoom or the ease to a selection).
      let queued = false;
      instance.getCamera().on("updated", () => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => {
          queued = false;
          if (!cancelled) relabelNow.current(latestSelected.current);
        });
      });
      relabelNow.current(latestSelected.current);
      sigma.current = instance;
      performance.mark("graph-rendered");
    });
    return () => {
      cancelled = true;
      relabelNow.current = () => {};
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
    relabelNow.current(selected);
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
