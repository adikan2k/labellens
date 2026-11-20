import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { GraphEdge, GraphNeighborhood, GraphNode } from "@/lib/api";
import { GRAPH } from "@/lib/copy";
import { columns, groupByKind, KIND_SHAPE, PEER_LIMIT, productCode } from "@/lib/graph-view";

const node = (id: string, kind: GraphNode["kind"], name: string, extra: Partial<GraphNode> = {}): GraphNode => ({
  id,
  kind,
  name,
  nutriscore_grade: null,
  detail: null,
  ...extra,
});
const link = (from: string, to: string, type: GraphEdge["type"] = "HAS_INGREDIENT"): GraphEdge => ({
  from,
  to,
  type,
});

const source: GraphNeighborhood["source"] = {
  name: "Open Food Facts",
  url: "https://world.openfoodfacts.org",
  licence: "ODbL-1.0",
  licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
  snapshot_date: "2026-11-17",
};

const BRAND = "Brand:general mills";
const CEREALS = "Category:cereals";
const GRAINS = "Category:grains";
const E307 = "Additive:en:e307";
const OATS = "Ingredient:en:oats";
const SUGAR = "Ingredient:en:sugar";

/** Cheerios, six things it is linked to, and four other products that share some of them. */
const DATA: GraphNeighborhood = {
  center: "Product:1",
  nodes: [
    node("Product:1", "Product", "Cheerios", { nutriscore_grade: "c" }),
    node(BRAND, "Brand", "General Mills"),
    node(CEREALS, "Category", "Breakfast cereals"),
    node(GRAINS, "Category", "Cereals and grains"),
    node(E307, "Additive", "E307 Tocopherol", { detail: "A form of vitamin E." }),
    node(OATS, "Ingredient", "Oats"),
    node(SUGAR, "Ingredient", "Sugar"),
    node("Product:2", "Product", "Wheaties", { nutriscore_grade: "b" }),
    node("Product:3", "Product", "Oat Bar"),
    node("Product:4", "Product", "Cheerios"), // the centre again, under another barcode
    node("Product:5", "Product", "wheaties!"), // Wheaties again, sharing less
  ],
  edges: [
    link("Product:1", BRAND, "MADE_BY"),
    link("Product:1", CEREALS, "IN"),
    link(CEREALS, GRAINS, "CHILD_OF"),
    link("Product:1", E307, "CONTAINS"),
    link("Product:1", OATS),
    link("Product:1", SUGAR),
    link("Product:2", BRAND, "MADE_BY"),
    link("Product:2", BRAND, "MADE_BY"), // repeated: counted once
    link("Product:2", CEREALS, "IN"),
    link("Product:2", SUGAR),
    link("Product:3", OATS),
    link("Product:4", BRAND, "MADE_BY"),
    link("Product:4", OATS),
    link("Product:5", SUGAR),
  ],
  truncated: true,
  source,
};

describe("graph view", () => {
  test("three columns: the product, what it is linked to by kind, and what shares it", () => {
    const model = columns(DATA, DATA.center)!;
    expect(model.center.name).toBe("Cheerios");
    expect(model.groups.map((g) => [g.kind, g.hubs.map((h) => h.node.name)])).toEqual([
      ["Brand", ["General Mills"]],
      // The wider category is reached only through the narrower one: listed, not linked.
      ["Category", ["Breakfast cereals", "Cereals and grains"]],
      ["Additive", ["E307 Tocopherol"]],
      ["Ingredient", ["Oats", "Sugar"]],
    ]);
    const grains = model.groups[1].hubs[1];
    expect(grains.direct).toBe(false);
    expect(model.groups[0].hubs[0]).toMatchObject({ direct: true, products: ["Product:2", "Product:4"] });
    expect(model.focus).toBeNull();
  });

  test("peers are ranked by what they share, once per name, without the centre's other listings", () => {
    const model = columns(DATA, DATA.center)!;
    expect(model.peers.map((p) => [p.node.id, p.shares])).toEqual([
      ["Product:2", [BRAND, CEREALS, SUGAR]],
      ["Product:3", [OATS]],
    ]);
    // "Cheerios" again is the centre under another barcode; "wheaties!" is Wheaties sharing less.
    expect(model.peersTotal).toBe(2);
  });

  test("selecting a hub narrows the right column to the products linked to it", () => {
    const model = columns(DATA, OATS)!;
    expect(model.focus?.name).toBe("Oats");
    expect(model.peers.map((p) => p.node.name)).toEqual(["Oat Bar"]);
    expect(columns(DATA, E307)!.peers).toEqual([]);
  });

  test("the right column stops at the limit, and still shows a product chosen from the list", () => {
    const many: GraphNeighborhood = {
      ...DATA,
      nodes: [
        ...DATA.nodes,
        ...Array.from({ length: PEER_LIMIT + 4 }, (_, i) => node(`Product:x${i}`, "Product", `Extra ${i}`)),
      ],
      edges: [
        ...DATA.edges,
        ...Array.from({ length: PEER_LIMIT + 4 }, (_, i) => link(`Product:x${i}`, SUGAR)),
      ],
    };
    const model = columns(many, many.center)!;
    expect(model.peers).toHaveLength(PEER_LIMIT);
    expect(model.peersTotal).toBe(PEER_LIMIT + 6);
    const last = `Product:x${PEER_LIMIT + 3}`;
    expect(model.peers.some((p) => p.node.id === last)).toBe(false);
    const chosen = columns(many, last)!;
    expect(chosen.peers).toHaveLength(PEER_LIMIT + 1);
    expect(chosen.peers.at(-1)?.node.id).toBe(last);
    // The folded listing can still be chosen by its own id.
    expect(columns(DATA, "Product:5")!.peers.at(-1)?.node.id).toBe("Product:5");
  });

  test("a neighbourhood without its centre draws nothing", () => {
    expect(columns({ ...DATA, center: "Product:404" }, "Product:404")).toBeNull();
  });

  test("each kind has its own shape; products and ingredients share the dot", () => {
    expect(KIND_SHAPE).toEqual({
      Product: "circle",
      Brand: "square",
      Category: "diamond",
      Additive: "triangle",
      Ingredient: "circle",
    });
  });

  test("groups by kind with the centre first; product ids", () => {
    const groups = groupByKind(DATA);
    expect(groups.map(([kind]) => kind)).toEqual(["Product", "Brand", "Category", "Additive", "Ingredient"]);
    expect(groups[0][1][0].id).toBe("Product:1");
    expect(productCode("Product:0016000275287")).toBe("0016000275287");
    expect(productCode(BRAND)).toBeNull();
  });
});

const api = vi.hoisted(() => ({ getNeighborhood: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  getNeighborhood: api.getNeighborhood,
}));

const { GraphExplorer, NOT_IN_GRAPH } = await import("./graph-explorer");
const { ApiError } = await import("@/lib/api");

afterEach(() => {
  cleanup();
  api.getNeighborhood.mockReset();
});

/** The three-column drawing; the list view below it repeats every node. */
const drawing = () => within(screen.getByTestId("graph-columns"));
const pressed = () =>
  drawing()
    .getAllByRole("button", { pressed: true })
    .map((b) => b.getAttribute("data-node"));

describe("GraphExplorer", () => {
  test("shows the centre product in the panel, and the three columns", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    const panel = await screen.findByRole("region", { name: "Selected node" });
    expect(within(panel).getByText("This product")).toBeTruthy();
    expect(within(panel).getByRole("heading", { name: "Cheerios" })).toBeTruthy();
    expect(within(panel).getByRole("img", { name: "Nutri-Score C" })).toBeTruthy();
    expect(api.getNeighborhood).toHaveBeenCalledWith("1", expect.objectContaining({ depth: 2 }));
    expect(screen.getByText(/11 nodes, the best-ranked shown/)).toBeTruthy();

    expect(screen.getByRole("region", { name: GRAPH.centre })).toBeTruthy();
    const hubs = within(screen.getByRole("region", { name: GRAPH.hubs }));
    // The headings are the key: each kind is named beside its marks, with how many.
    expect(hubs.getAllByRole("heading").map((h) => h.textContent)).toEqual([
      "Brands (1)",
      "Categories (2)",
      "Additives (1)",
      "Ingredients (2)",
    ]);
    const peers = within(screen.getByRole("region", { name: GRAPH.peers }));
    expect(peers.getByRole("heading").textContent).toBe(GRAPH.peersTop);
    expect(peers.getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
      "Wheaties, 3 in common",
      "Oat Bar, 1 in common",
    ]);
    expect(pressed()).toEqual(["Product:1"]);
  });

  test("selecting something it is linked to lists the products that share it", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    fireEvent.click(drawing().getByRole("button", { name: "Oats" }));
    expect(pressed()).toEqual([OATS]);
    const peers = within(screen.getByRole("region", { name: GRAPH.peers }));
    expect(peers.getByRole("heading").textContent).toBe("Others with Oats");
    expect(peers.getAllByRole("button").map((b) => b.getAttribute("data-node"))).toEqual(["Product:3"]);
    const panel = screen.getByRole("region", { name: "Selected node" });
    // The same count as the column beside it: Oat Bar, once.
    expect(within(panel).getByText("This product and 1 of the others shown are linked to it.")).toBeTruthy();

    fireEvent.click(drawing().getByRole("button", { name: "E307 Tocopherol" }));
    expect(within(panel).getByText("A form of vitamin E.")).toBeTruthy();
    expect(within(panel).getByText("Written by AI from Open Food Facts data.")).toBeTruthy();
    expect(screen.getByText(GRAPH.noPeers)).toBeTruthy();
    expect(within(panel).getByText("Of the products shown, only this one is linked to it.")).toBeTruthy();

    fireEvent.click(drawing().getByRole("button", { name: "Cereals and grains" }));
    expect(within(panel).getByText(GRAPH.widerCategory)).toBeTruthy();
  });

  test("selecting another product says what it has in common with the centre", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    fireEvent.click(drawing().getByRole("button", { name: "Wheaties, 3 in common" }));
    const panel = within(screen.getByRole("region", { name: "Selected node" }));
    expect(panel.getByRole("heading", { name: "In common with Cheerios (3)" })).toBeTruthy();
    expect(panel.getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "General Mills",
      "Breakfast cereals",
      "Sugar",
    ]);
  });

  test("lines are drawn between measured rows; the selected node's are strong; none is announced", async () => {
    // jsdom lays nothing out, so give every element a box: the lines wait for one.
    const box = vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({
      top: 10,
      height: 20,
      bottom: 30,
      left: 0,
      right: 100,
      width: 100,
      x: 0,
      y: 10,
      toJSON: () => ({}),
    });
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    const drawn = () => screen.getByTestId("graph-columns").querySelectorAll("[data-lines] path");
    // Five from the centre (the wider category has none), four to the two peers.
    await waitFor(() => expect(drawn()).toHaveLength(9));
    fireEvent.click(drawing().getByRole("button", { name: "Wheaties, 3 in common" }));
    await waitFor(() =>
      expect(screen.getByTestId("graph-columns").querySelectorAll("path.stroke-ink")).toHaveLength(3),
    );
    for (const lines of screen.getByTestId("graph-columns").querySelectorAll("[data-lines]")) {
      expect(lines.getAttribute("aria-hidden")).toBe("true");
    }
    box.mockRestore();
  });

  test("another product becomes the centre without a page load", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    const push = vi.spyOn(window.history, "pushState");
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    fireEvent.click(drawing().getByRole("button", { name: "Wheaties, 3 in common" }));
    fireEvent.click(screen.getByRole("button", { name: "Centre the graph here" }));
    expect(push).toHaveBeenCalledWith(null, "", "/graph?code=2");
    await waitFor(() =>
      expect(api.getNeighborhood).toHaveBeenLastCalledWith("2", expect.objectContaining({ depth: 2 })),
    );
    push.mockRestore();
  });

  test("the list view holds every node, and choosing one there selects it", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    const list = within(screen.getByRole("region", { name: "Products" }));
    expect(list.getAllByRole("button")).toHaveLength(5);
    fireEvent.click(list.getByRole("button", { name: "wheaties!" }));
    // A listing folded out of the column is added to it while it is selected.
    expect(pressed()).toEqual(["Product:5"]);
  });

  test("data fetched on the server is drawn without another request", () => {
    render(<GraphExplorer code="1" initial={DATA} />);
    expect(screen.getByRole("region", { name: "Selected node" })).toBeTruthy();
    expect(api.getNeighborhood).not.toHaveBeenCalled();
  });

  test("a product the graph does not hold says so and links to its page", async () => {
    api.getNeighborhood.mockRejectedValue(new ApiError(404, "not held"));
    render(<GraphExplorer code="9" />);
    await waitFor(() => expect(screen.getByText(NOT_IN_GRAPH)).toBeTruthy());
    expect(screen.getByRole("link", { name: "Open the product page" }).getAttribute("href")).toBe(
      "/product/9",
    );
  });
});
