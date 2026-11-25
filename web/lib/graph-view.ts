/**
 * Turns a /graph/neighborhood response into the three columns the graph page draws, and the
 * groupings the side panel and the list view use. Pure, so it is tested without a browser.
 *
 * A neighbourhood always has the same three layers: one product, the things it is linked to
 * (its brand, categories, additives and ingredients, the "hubs"), and the other products linked
 * to those same things (its "peers"). DESIGN.md, Graph explorer: the layers are drawn left to
 * right, so where a node sits says what it is.
 */
import type { GraphNeighborhood, GraphNode } from "./api";

export type NodeShape = "circle" | "square" | "diamond" | "triangle";
type Kind = GraphNode["kind"];
export type HubKind = Exclude<Kind, "Product">;

/** One shape per kind, so the kinds can be told apart without colour (DESIGN.md). */
export const KIND_SHAPE: Record<Kind, NodeShape> = {
  Product: "circle",
  Brand: "square",
  Category: "diamond",
  Additive: "triangle",
  Ingredient: "circle",
};

export const KIND_ORDER: Kind[] = ["Product", "Brand", "Category", "Additive", "Ingredient"];
export const KIND_NAMES: Record<Kind, string> = {
  Product: "Products",
  Brand: "Brands",
  Category: "Categories",
  Additive: "Additives",
  Ingredient: "Ingredients",
};

/** How many peers the right column lists before a hub is chosen. */
export const PEER_LIMIT = 16;

/** Products in the graph (decision 0006). Only the weights' relative sizes matter. */
const GRAPH_PRODUCTS = 27_662;

/**
 * What sharing this hub is worth: more for a rare one (a brand, a particular phosphate)
 * than for salt, which thousands of products list. Inverse document frequency on how many
 * links point to the hub in the whole graph (`degree`); 1 when the API does not say.
 */
export function hubWeight(degree: number | null | undefined): number {
  if (degree === null || degree === undefined) return 1;
  return Math.log(GRAPH_PRODUCTS / (1 + Math.max(degree, 0)));
}

/** Something the centre product is linked to, and the other products linked to it too. */
export type Hub = {
  node: GraphNode;
  /** False for a wider category the centre is in only through a narrower one. */
  direct: boolean;
  /** The other products linked to it, by node id. */
  products: string[];
};
export type HubGroup = { kind: HubKind; hubs: Hub[] };

/** Another product, the hubs it has in common with the centre, and what they are worth. */
export type Peer = { node: GraphNode; shares: string[]; score: number };

export type Columns = {
  center: GraphNode;
  groups: HubGroup[];
  /** The right column, best match first. */
  peers: Peer[];
  /** Every other product in the neighbourhood, once per name. */
  peersTotal: number;
  /** The hub the right column is narrowed to, when one is selected. */
  focus: GraphNode | null;
};

/** Case and punctuation aside: Open Food Facts lists one product under several barcodes. */
function fold(name: string): string {
  return (name.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []).join(" ");
}

/**
 * The three columns for a neighbourhood.
 *
 * - Hubs are grouped by kind; in a group, the ones the centre is linked to directly come
 *   first, then the ones with the most other products.
 * - Peers are ranked by `score`, the sum of hubWeight over what they share, so two products
 *   that both list salt and sugar rank below two that share a brand or a rare additive.
 * - Peers are listed once per name (the listing that scores highest), and listings with the
 *   centre's own name are left out: they are the same product under another barcode.
 * - With the centre or a peer selected, the right column holds the PEER_LIMIT best-scoring
 *   peers. With a hub selected, it holds every peer linked to that hub.
 */
export function columns(data: GraphNeighborhood, selected: string): Columns | null {
  const center = data.nodes.find((n) => n.id === data.center);
  if (!center) return null;
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const isProduct = (id: string) => byId.get(id)?.kind === "Product";

  const direct = new Set(data.edges.filter((e) => e.from === center.id).map((e) => e.to));
  const productsOf = new Map<string, string[]>();
  for (const edge of data.edges) {
    if (edge.from === center.id || !isProduct(edge.from) || isProduct(edge.to)) continue;
    const list = productsOf.get(edge.to) ?? [];
    if (!list.includes(edge.from)) list.push(edge.from);
    productsOf.set(edge.to, list);
  }

  const groups: HubGroup[] = [];
  for (const kind of KIND_ORDER) {
    if (kind === "Product") continue;
    const hubs = data.nodes
      .filter((n) => n.kind === kind)
      .map((node) => ({ node, direct: direct.has(node.id), products: productsOf.get(node.id) ?? [] }))
      .sort(
        (a, b) =>
          Number(b.direct) - Number(a.direct) ||
          b.products.length - a.products.length ||
          a.node.name.localeCompare(b.node.name),
      );
    if (hubs.length) groups.push({ kind, hubs });
  }
  const hubOrder = new Map(groups.flatMap((g) => g.hubs).map((hub, i) => [hub.node.id, i]));

  // Every other product with what it shares, then one per name.
  const weight = new Map(data.nodes.map((n) => [n.id, hubWeight(n.degree)]));
  const all: Peer[] = data.nodes
    .filter((n) => n.kind === "Product" && n.id !== center.id)
    .map((node) => {
      const shares = [...hubOrder.keys()].filter(
        (hub) => direct.has(hub) && (productsOf.get(hub) ?? []).includes(node.id),
      );
      const score = shares.reduce((sum, hub) => sum + (weight.get(hub) ?? 1), 0);
      return { node, shares, score };
    });
  const centerName = fold(center.name);
  const byName = new Map<string, Peer>();
  for (const peer of all) {
    const name = fold(peer.node.name);
    if (name === centerName) continue;
    const kept = byName.get(name);
    if (!kept || peer.score > kept.score) byName.set(name, peer);
  }
  const middle = (peer: Peer) =>
    peer.shares.reduce((sum, hub) => sum + (hubOrder.get(hub) ?? 0), 0) / (peer.shares.length || 1);
  const ranked = [...byName.values()].sort(
    (a, b) => b.score - a.score || b.shares.length - a.shares.length || middle(a) - middle(b),
  );

  const chosen = byId.get(selected);
  const focus = chosen && chosen.kind !== "Product" ? chosen : null;
  let peers = focus
    ? ranked.filter((peer) => (productsOf.get(focus.id) ?? []).includes(peer.node.id))
    : ranked.slice(0, PEER_LIMIT);
  // A product picked from the list view is shown even when it did not make the column.
  if (chosen && chosen.kind === "Product" && chosen.id !== center.id) {
    const own = all.find((peer) => peer.node.id === chosen.id);
    if (own && !peers.some((peer) => peer.node.id === chosen.id)) peers = [...peers, own];
  }
  return { center, groups, peers, peersTotal: ranked.length, focus };
}

/** Nodes grouped by kind (centre first among products), for the panel and the list view. */
export function groupByKind(data: GraphNeighborhood): [Kind, GraphNode[]][] {
  return KIND_ORDER.map((kind) => {
    const nodes = data.nodes
      .filter((n) => n.kind === kind)
      .sort((a, b) => Number(b.id === data.center) - Number(a.id === data.center));
    return [kind, nodes] as [Kind, GraphNode[]];
  }).filter(([, nodes]) => nodes.length > 0);
}

/** The barcode in a product node id ("Product:0016000275287" -> "0016000275287"). */
export function productCode(nodeId: string): string | null {
  return nodeId.startsWith("Product:") ? nodeId.slice("Product:".length) : null;
}
