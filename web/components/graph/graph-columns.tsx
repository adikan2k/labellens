"use client";

import { useEffect, useRef, useState } from "react";

import type { GraphNeighborhood, GraphNode, NutriscoreGrade } from "@/lib/api";
import { GRAPH } from "@/lib/copy";
import { columns, type Hub, KIND_NAMES, KIND_SHAPE, type NodeShape, type Peer } from "@/lib/graph-view";

type Props = {
  data: GraphNeighborhood;
  selected: string;
  onSelect: (nodeId: string) => void;
};

const GRADE_TEXT: Record<NutriscoreGrade, string> = {
  a: "text-grade-a",
  b: "text-grade-b",
  c: "text-grade-c",
  d: "text-grade-d",
  e: "text-grade-e",
};

/** One of the graph's marks: a shape per kind of node (KIND_SHAPE). */
export function Mark({ shape, className = "" }: { shape: NodeShape; className?: string }) {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" className={`inline-block h-3 w-3 shrink-0 ${className}`}>
      {shape === "circle" && <circle cx="6" cy="6" r="5" fill="currentColor" />}
      {shape === "square" && <rect x="1" y="1" width="10" height="10" fill="currentColor" />}
      {shape === "diamond" && <path d="M6 0 12 6 6 12 0 6Z" fill="currentColor" />}
      {shape === "triangle" && <path d="M6 1 11.5 11H.5Z" fill="currentColor" />}
    </svg>
  );
}

type Link = { from: string; to: string };
/** Where each row's middle is, in pixels from the top of the columns, and how tall they are. */
type Geometry = { height: number; y: Record<string, number> };
const NO_GEOMETRY: Geometry = { height: 0, y: {} };

/**
 * The lines between two neighbouring columns, from the left edge to the right edge. Names wrap
 * (DESIGN.md: no label is cut off), so rows differ in height and the ends are measured.
 */
function Lines({
  links,
  geometry,
  active,
  curved = false,
}: {
  links: Link[];
  geometry: Geometry;
  active: string | null;
  /** A fan from one point reads best curved; many crossing lines read best straight. */
  curved?: boolean;
}) {
  const strong = (link: Link) => active !== null && (link.from === active || link.to === active);
  const measured = links.filter((l) => l.from in geometry.y && l.to in geometry.y);
  // Strong lines last, so they are drawn over the light ones.
  const ordered = [...measured].sort((a, b) => Number(strong(a)) - Number(strong(b)));
  return (
    <div data-lines aria-hidden="true" className="relative hidden md:block">
      <svg
        viewBox={`0 0 100 ${Math.max(geometry.height, 1)}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full"
      >
        {ordered.map((link) => {
          const [y1, y2] = [geometry.y[link.from], geometry.y[link.to]];
          return (
            <path
              key={`${link.from}>${link.to}`}
              d={curved ? `M0 ${y1}C50 ${y1} 50 ${y2} 100 ${y2}` : `M0 ${y1}L100 ${y2}`}
              fill="none"
              vectorEffect="non-scaling-stroke"
              strokeWidth={strong(link) ? 1.5 : 1}
              className={strong(link) ? "stroke-ink" : "stroke-rule-light"}
            />
          );
        })}
      </svg>
    </div>
  );
}

function Row({
  node,
  shape,
  markClass = "",
  count,
  state,
  selected,
  onSelect,
  onHover,
}: {
  node: GraphNode;
  shape: NodeShape;
  markClass?: string;
  /** For a peer: how many of the middle column it shares with the centre. */
  count?: number;
  /** How the row relates to what is selected or pointed at. */
  state: "plain" | "related" | "faded";
  selected: boolean;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  const tone = selected
    ? "bg-ink text-paper"
    : state === "faded"
      ? "text-ink-muted"
      : state === "related"
        ? "font-bold"
        : "";
  return (
    <button
      type="button"
      data-node={node.id}
      aria-pressed={selected}
      aria-label={count === undefined ? undefined : `${node.name}, ${count} ${GRAPH.inCommon}`}
      onClick={() => onSelect(node.id)}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(node.id)}
      onBlur={() => onHover(null)}
      className={`type-small flex min-h-8 w-full cursor-pointer items-center gap-2 px-2 py-1 text-left ${tone}`}
    >
      <Mark shape={shape} className={selected ? "" : markClass} />
      <span className="min-w-0 flex-1 break-words">{node.name}</span>
      {count !== undefined && <span className="shrink-0">{count}</span>}
    </button>
  );
}

/**
 * The neighbourhood as three columns: this product, what it is linked to, and the products
 * that share those things. Everything is an ordinary button in a list, so it works by keyboard
 * and screen reader; the lines between the columns are decoration and are hidden from both.
 * Below `md` the columns stack and the lines are left out: the bold rows show what is linked.
 */
export function GraphColumns({ data, selected, onSelect }: Props) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [geometry, setGeometry] = useState<Geometry>(NO_GEOMETRY);
  const root = useRef<HTMLDivElement>(null);

  // Measure where each row's middle is, after every change that can move a row: the data, the
  // selection (it changes the right column), the width, and the web font arriving.
  useEffect(() => {
    const element = root.current;
    if (!element) return;
    const measure = () => {
      const origin = element.querySelector("[data-lines]")?.getBoundingClientRect();
      if (!origin || origin.height === 0) {
        setGeometry(NO_GEOMETRY); // stacked on a phone: no lines
        return;
      }
      const y: Record<string, number> = {};
      for (const row of element.querySelectorAll<HTMLElement>("[data-node]")) {
        const box = row.getBoundingClientRect();
        y[row.dataset.node!] = box.top + box.height / 2 - origin.top;
      }
      setGeometry({ height: origin.height, y });
    };
    const frame = requestAnimationFrame(measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(element);
    void document.fonts?.ready.then(measure);
    performance.mark("graph-rendered");
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
    };
  }, [data, selected]);

  const model = columns(data, selected);
  if (!model) return null;
  const { center, groups, peers, focus } = model;
  const hubs = groups.flatMap((g) => g.hubs);
  const active = hovered ?? selected;

  const left: Link[] = hubs.filter((hub) => hub.direct).map((hub) => ({ from: center.id, to: hub.node.id }));
  const right: Link[] = peers.flatMap((peer) => peer.shares.map((hub) => ({ from: hub, to: peer.node.id })));

  const related = new Set<string>();
  if (active !== center.id) {
    for (const link of [...left, ...right]) {
      if (link.from === active) related.add(link.to);
      if (link.to === active) related.add(link.from);
    }
  }
  const stateOf = (id: string): "plain" | "related" | "faded" => {
    if (active === center.id || id === active) return "plain";
    return related.has(id) ? "related" : "faded";
  };
  const hubRow = (hub: Hub) => (
    <li key={hub.node.id}>
      <Row
        node={hub.node}
        shape={KIND_SHAPE[hub.node.kind]}
        markClass={hub.node.kind === "Ingredient" || !hub.direct ? "text-ink-muted" : ""}
        state={stateOf(hub.node.id)}
        selected={selected === hub.node.id}
        onSelect={onSelect}
        onHover={setHovered}
      />
    </li>
  );
  const peerRow = (peer: Peer) => (
    <li key={peer.node.id}>
      <Row
        node={peer.node}
        shape="circle"
        count={peer.shares.length}
        state={stateOf(peer.node.id)}
        selected={selected === peer.node.id}
        onSelect={onSelect}
        onHover={setHovered}
      />
    </li>
  );

  return (
    <div
      ref={root}
      data-testid="graph-columns"
      className="panel grid grid-cols-1 gap-y-4 p-3 md:grid-cols-[minmax(7rem,10rem)_minmax(2rem,1fr)_minmax(10rem,14rem)_minmax(2rem,1fr)_minmax(11rem,18rem)] md:gap-y-0"
    >
      <section aria-label={GRAPH.centre} className="md:flex md:items-center">
        <div className="w-full">
          <h3 className="type-data-label px-2 pt-2 pb-1 md:sr-only">{GRAPH.centre}</h3>
          <Row
            node={center}
            shape="circle"
            markClass={center.nutriscore_grade ? GRADE_TEXT[center.nutriscore_grade] : ""}
            state="plain"
            selected={selected === center.id}
            onSelect={onSelect}
            onHover={setHovered}
          />
        </div>
      </section>

      <Lines links={left} geometry={geometry} active={active} curved />

      <section aria-label={GRAPH.hubs}>
        {groups.map((group) => (
          <div key={group.kind}>
            <h3 className="type-data-label px-2 pt-2 pb-1">
              {KIND_NAMES[group.kind]} ({group.hubs.length})
            </h3>
            <ul>{group.hubs.map(hubRow)}</ul>
          </div>
        ))}
      </section>

      <Lines links={right} geometry={geometry} active={active} />

      <section aria-label={GRAPH.peers}>
        <h3 className="type-data-label px-2 pt-2 pb-1">
          {focus ? GRAPH.peersOf(focus.name) : GRAPH.peersTop}
        </h3>
        {peers.length > 0 ? (
          <ul>{peers.map(peerRow)}</ul>
        ) : (
          <p className="type-small px-2 py-1">{GRAPH.noPeers}</p>
        )}
      </section>
    </div>
  );
}
