import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { GraphNeighborhood } from "@/lib/api";
import {
  degree,
  groupByKind,
  layout,
  pickLabels,
  productCode,
  toGraph,
  type Tokens,
} from "@/lib/graph-view";

const TOKENS: Tokens = {
  ink: "ink",
  inkMuted: "ink-muted",
  ruleLight: "rule-light",
  grade: { a: "grade-a", b: "grade-b", c: "grade-c", d: "grade-d", e: "grade-e" },
};

const DATA: GraphNeighborhood = {
  center: "Product:1",
  nodes: [
    { id: "Product:1", kind: "Product", name: "Cheerios", nutriscore_grade: "c", detail: null },
    { id: "Brand:general mills", kind: "Brand", name: "General Mills", nutriscore_grade: null, detail: null },
    { id: "Additive:en:e307", kind: "Additive", name: "E307 Tocopherol", nutriscore_grade: null, detail: "A form of vitamin E." },
    { id: "Product:2", kind: "Product", name: "Wheaties", nutriscore_grade: "b", detail: null },
  ],
  edges: [
    { from: "Product:1", to: "Brand:general mills", type: "MADE_BY" },
    { from: "Product:1", to: "Additive:en:e307", type: "CONTAINS" },
    { from: "Product:2", to: "Brand:general mills", type: "MADE_BY" },
    { from: "Product:2", to: "Brand:general mills", type: "MADE_BY" },
  ],
  truncated: true,
  source: {
    name: "Open Food Facts",
    url: "https://world.openfoodfacts.org",
    licence: "ODbL-1.0",
    licence_url: "https://opendatacommons.org/licenses/odbl/1-0/",
    snapshot_date: "2026-11-17",
  },
};

describe("graph view", () => {
  test("the centre is the only node in a grade colour; the rest are ink, edges rule-light", () => {
    const graph = toGraph(DATA, TOKENS);
    expect(graph.order).toBe(4);
    expect(graph.size).toBe(3); // the repeated edge is drawn once
    expect(graph.getNodeAttribute("Product:1", "color")).toBe("grade-c");
    expect(graph.getNodeAttribute("Product:2", "color")).toBe("ink");
    expect(graph.getNodeAttribute("Brand:general mills", "color")).toBe("ink-muted");
    expect(graph.getNodeAttribute("Product:1", "size")).toBeGreaterThan(
      graph.getNodeAttribute("Product:2", "size"),
    );
    graph.forEachEdge((_, attrs) => expect(attrs.color).toBe("rule-light"));
  });

  test("the layout is finite, deterministic and centred on the product", () => {
    const first = toGraph(DATA, TOKENS);
    const second = toGraph(DATA, TOKENS);
    layout(first, DATA.center);
    layout(second, DATA.center);
    expect(first.getNodeAttributes("Product:1")).toMatchObject({ x: 0, y: 0 });
    first.forEachNode((id, attrs) => {
      expect(Number.isFinite(attrs.x) && Number.isFinite(attrs.y)).toBe(true);
      expect(second.getNodeAttributes(id).x).toBeCloseTo(attrs.x);
    });
  });

  test("groups by kind with the centre first; ids and degrees", () => {
    const groups = groupByKind(DATA);
    expect(groups.map(([kind]) => kind)).toEqual(["Product", "Brand", "Additive"]);
    expect(groups[0][1][0].id).toBe("Product:1");
    expect(productCode("Product:0016000275287")).toBe("0016000275287");
    expect(productCode("Brand:x")).toBeNull();
    expect(degree(DATA, "Brand:general mills")).toBe(3);
  });

  test("labels never overlap; forced labels win, then priority", () => {
    const box = (id: string, left: number, top: number, width = 100) => ({
      id,
      left,
      top,
      width,
      height: 16,
    });
    const boxes = [
      box("center", 0, 0),
      box("busy", 50, 8), // overlaps the centre
      box("near", 0, 18), // 2 px below the centre: inside the padding
      box("clear", 0, 40),
      box("low", 10, 44), // overlaps "clear", which ranks higher
      box("selected", 300, 0),
      box("crowded", 320, 4), // overlaps the selected node
    ];
    const rank: Record<string, number> = { busy: 9, near: 1, clear: 5, low: 4, crowded: 99 };
    const shown = pickLabels(boxes, ["center", "selected"], (id) => rank[id] ?? 0);
    expect([...shown].sort()).toEqual(["center", "clear", "selected"]);
    const kept = boxes.filter((b) => shown.has(b.id));
    for (const a of kept) {
      for (const b of kept) {
        if (a === b) continue;
        const apart =
          a.left + a.width <= b.left || b.left + b.width <= a.left || a.top + a.height <= b.top || b.top + b.height <= a.top;
        expect(apart).toBe(true);
      }
    }
  });

  test("labels cover no other node's dot and stay inside the canvas", () => {
    const label = (id: string, left: number) => ({ id, left, top: 0, width: 60, height: 16 });
    const dot = (id: string, left: number) => ({ id, left, top: 4, width: 8, height: 8 });
    const shown = pickLabels(
      [label("a", 0), label("b", 200), label("c", 120)],
      [],
      () => 0,
      {
        dots: [dot("a", -10), dot("b", 190), dot("x", 30), dot("c", 110)],
        bounds: { width: 300, height: 100 },
      },
    );
    // a covers x's dot; b's own dot does not count against it; c fits.
    expect([...shown].sort()).toEqual(["b", "c"]);
    const outside = pickLabels([label("edge", 260), label("centre", 260)], ["centre"], () => 0, {
      bounds: { width: 300, height: 100 },
    });
    expect([...outside]).toEqual(["centre"]); // only a forced label may run past the edge
  });

  test("forced labels show even when they overlap each other", () => {
    const shown = pickLabels(
      [
        { id: "a", left: 0, top: 0, width: 50, height: 16 },
        { id: "b", left: 10, top: 0, width: 50, height: 16 },
      ],
      ["a", "b"],
      () => 0,
    );
    expect(shown).toEqual(new Set(["a", "b"]));
  });
});

const api = vi.hoisted(() => ({ getNeighborhood: vi.fn() }));
vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  getNeighborhood: api.getNeighborhood,
}));
vi.mock("./graph-canvas", () => ({ GraphCanvas: () => <div data-testid="graph-canvas" /> }));

const { GraphExplorer, NOT_IN_GRAPH } = await import("./graph-explorer");
const { ApiError } = await import("@/lib/api");

afterEach(() => {
  cleanup();
  api.getNeighborhood.mockReset();
});

describe("GraphExplorer", () => {
  test("shows the centre product in the panel, and the nodes as a list", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    const panel = await screen.findByRole("region", { name: "Selected node" });
    expect(within(panel).getByText("This product")).toBeTruthy();
    expect(within(panel).getByRole("heading", { name: "Cheerios" })).toBeTruthy();
    expect(within(panel).getByRole("img", { name: "Nutri-Score C" })).toBeTruthy();
    expect(api.getNeighborhood).toHaveBeenCalledWith("1", expect.objectContaining({ depth: 2 }));
    expect(screen.getByText(/4 nodes, the best-ranked shown/)).toBeTruthy();
  });

  test("selecting a node from the list shows it, with its explainer and the AI note", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    fireEvent.click(screen.getByRole("button", { name: "E307 Tocopherol" }));
    const panel = screen.getByRole("region", { name: "Selected node" });
    expect(within(panel).getByText("A form of vitamin E.")).toBeTruthy();
    expect(within(panel).getByText("Written by AI from Open Food Facts data.")).toBeTruthy();
  });

  test("another product becomes the centre without a page load", async () => {
    api.getNeighborhood.mockResolvedValue(DATA);
    const push = vi.spyOn(window.history, "pushState");
    render(<GraphExplorer code="1" />);
    await screen.findByRole("region", { name: "Selected node" });
    fireEvent.click(screen.getByRole("button", { name: "Wheaties" }));
    fireEvent.click(screen.getByRole("button", { name: "Centre the graph here" }));
    expect(push).toHaveBeenCalledWith(null, "", "/graph?code=2");
    await waitFor(() =>
      expect(api.getNeighborhood).toHaveBeenLastCalledWith("2", expect.objectContaining({ depth: 2 })),
    );
    push.mockRestore();
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
