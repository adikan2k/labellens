/**
 * Turns a /graph/neighborhood response into a laid-out graphology graph for Sigma, and the
 * groupings the side panel and the accessible list use. Pure, so it is tested without WebGL.
 *
 * DESIGN.md: nodes are black dots; the centre product is the only filled shape in its grade
 * colour; edges are rule-light. Colours come from the CSS tokens (readTokens), never from
 * hex codes here.
 */
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

import type { GraphNeighborhood, GraphNode, NutriscoreGrade } from "./api";

export type Tokens = {
  ink: string;
  inkMuted: string;
  ruleLight: string;
  grade: Record<NutriscoreGrade, string>;
};

/** The colour tokens from globals.css, read at runtime (WebGL needs real colour values). */
export function readTokens(root: Element = document.documentElement): Tokens {
  const style = getComputedStyle(root);
  const read = (name: string) => style.getPropertyValue(`--color-${name}`).trim();
  return {
    ink: read("ink"),
    inkMuted: read("ink-muted"),
    ruleLight: read("rule-light"),
    grade: { a: read("grade-a"), b: read("grade-b"), c: read("grade-c"), d: read("grade-d"), e: read("grade-e") },
  };
}

export type NodeAttributes = {
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  kind: GraphNode["kind"];
  grade: NutriscoreGrade | null;
  isCenter: boolean;
  /** Set by the canvas after each camera move: this label clears the others (pickLabels). */
  labelShown?: boolean;
};

// Screen pixels (Sigma's default sizing): small dots, the centre product clearly larger.
export const NODE_SIZE = { center: 9, product: 3.5, other: 3 };

// Kinds in a ring around the centre, so the layout starts readable and stays deterministic.
const RING: Record<GraphNode["kind"], number> = {
  Brand: 1,
  Category: 1,
  Additive: 1,
  Ingredient: 1,
  Product: 2,
};

export function toGraph(data: GraphNeighborhood, tokens: Tokens): Graph<NodeAttributes> {
  const graph = new Graph<NodeAttributes>({ type: "directed", multi: false });
  const others = data.nodes.filter((n) => n.id !== data.center);
  others.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1);
    const radius = 10 * RING[node.kind];
    graph.addNode(node.id, {
      x: radius * Math.cos(angle),
      y: radius * Math.sin(angle),
      size: node.kind === "Product" ? NODE_SIZE.product : NODE_SIZE.other,
      color: node.kind === "Product" ? tokens.ink : tokens.inkMuted,
      label: node.name,
      kind: node.kind,
      grade: node.nutriscore_grade ?? null,
      isCenter: false,
    });
  });
  const center = data.nodes.find((n) => n.id === data.center);
  if (center) {
    const grade = center.nutriscore_grade ?? null;
    graph.addNode(center.id, {
      x: 0,
      y: 0,
      size: NODE_SIZE.center,
      color: grade ? tokens.grade[grade] : tokens.ink,
      label: center.name,
      kind: center.kind,
      grade,
      isCenter: true,
    });
  }
  for (const edge of data.edges) {
    if (graph.hasNode(edge.from) && graph.hasNode(edge.to) && !graph.hasEdge(edge.from, edge.to)) {
      graph.addEdge(edge.from, edge.to, { color: tokens.ruleLight, size: 1 });
    }
  }
  return graph;
}

/** Lays the graph out in place (ForceAtlas2, fixed iterations), centre pinned at the origin. */
export function layout(graph: Graph<NodeAttributes>, center: string, iterations = 150): void {
  if (graph.order < 2) return;
  forceAtlas2.assign(graph, {
    iterations,
    settings: {
      ...forceAtlas2.inferSettings(graph),
      gravity: 0.5,
      scalingRatio: 30,
      adjustSizes: false,
      barnesHutOptimize: false,
    },
  });
  if (graph.hasNode(center)) {
    const { x, y } = graph.getNodeAttributes(center);
    graph.updateEachNodeAttributes((_, attrs) => ({ ...attrs, x: attrs.x - x, y: attrs.y - y }));
  }
}

/** A label's box on screen, in CSS pixels. */
export type LabelBox = { id: string; left: number; top: number; width: number; height: number };

function apart(a: Omit<LabelBox, "id">, b: Omit<LabelBox, "id">, padding: number): boolean {
  return (
    a.left >= b.left + b.width + padding ||
    b.left >= a.left + a.width + padding ||
    a.top >= b.top + b.height + padding ||
    b.top >= a.top + a.height + padding
  );
}

/**
 * Which labels to draw so that none overlap. The forced ones (the centre product, the
 * selected node) are kept first; the rest go in order of priority, each kept only if its box,
 * padded, clears every label already kept, covers no other node's dot (`dots`, keyed by node)
 * and fits inside `bounds`. Sigma's own label grid only caps labels per grid cell, so long
 * names in neighbouring cells ran into each other.
 */
export function pickLabels(
  boxes: LabelBox[],
  forced: readonly string[],
  priority: (id: string) => number,
  {
    padding = 4,
    dots = [],
    bounds,
  }: { padding?: number; dots?: LabelBox[]; bounds?: { width: number; height: number } } = {},
): Set<string> {
  const rank = (box: LabelBox) => {
    const i = forced.indexOf(box.id);
    return i >= 0 ? Number.MAX_SAFE_INTEGER - i : priority(box.id);
  };
  const ordered = [...boxes].sort((a, b) => rank(b) - rank(a) || a.id.localeCompare(b.id));
  const inside = (box: LabelBox) =>
    !bounds ||
    (box.left >= 0 &&
      box.top >= 0 &&
      box.left + box.width <= bounds.width &&
      box.top + box.height <= bounds.height);
  const kept: LabelBox[] = [];
  for (const box of ordered) {
    const clear =
      inside(box) &&
      kept.every((k) => apart(box, k, padding)) &&
      dots.every((d) => d.id === box.id || apart(box, d, 1));
    if (clear || forced.includes(box.id)) kept.push(box);
  }
  return new Set(kept.map((k) => k.id));
}

export const KIND_ORDER: GraphNode["kind"][] = ["Product", "Brand", "Category", "Additive", "Ingredient"];
export const KIND_NAMES: Record<GraphNode["kind"], string> = {
  Product: "Products",
  Brand: "Brands",
  Category: "Categories",
  Additive: "Additives",
  Ingredient: "Ingredients",
};

/** Nodes grouped by kind (centre first among products), for the panel and the list view. */
export function groupByKind(data: GraphNeighborhood): [GraphNode["kind"], GraphNode[]][] {
  return KIND_ORDER.map((kind) => {
    const nodes = data.nodes
      .filter((n) => n.kind === kind)
      .sort((a, b) => Number(b.id === data.center) - Number(a.id === data.center));
    return [kind, nodes] as [GraphNode["kind"], GraphNode[]];
  }).filter(([, nodes]) => nodes.length > 0);
}

/** The barcode in a product node id ("Product:0016000275287" -> "0016000275287"). */
export function productCode(nodeId: string): string | null {
  return nodeId.startsWith("Product:") ? nodeId.slice("Product:".length) : null;
}

/** How many of the shown nodes link to this one, for brand and category nodes in the panel. */
export function degree(data: GraphNeighborhood, nodeId: string): number {
  return data.edges.filter((e) => e.to === nodeId || e.from === nodeId).length;
}
