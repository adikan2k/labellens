"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { GradeChip, Panel, Rule } from "@/components/label/primitives";
import type { NutriscoreGrade } from "@/lib/api";
import { ApiError, getNeighborhood, type GraphNeighborhood, type GraphNode } from "@/lib/api";
import { AI_NOTE } from "@/lib/copy";
import {
  degree,
  groupByKind,
  keyEntries,
  KIND_NAMES,
  type NodeShape,
  productCode,
} from "@/lib/graph-view";

import { GraphCanvas } from "./graph-canvas";

type Outcome = { code: string; data: GraphNeighborhood } | { code: string; error: ApiError };

export const NOT_IN_GRAPH =
  "The graph holds the most complete graded products, and this one is not among them.";

/**
 * The graph explorer: a product's neighbourhood drawn with Sigma, a label-style panel for the
 * selected node, and the same nodes as a list, so everything works by keyboard and screen
 * reader too (the WebGL canvas itself is hidden from assistive technology).
 */
export function GraphExplorer({
  code: firstCode,
  initial = null,
}: {
  code: string;
  /** The neighbourhood fetched while the server rendered the page, so the first draw waits for nothing. */
  initial?: GraphNeighborhood | null;
}) {
  // Re-centring stays in the browser: the address changes with history.pushState and only the
  // neighbourhood is fetched, without a server render of the page.
  const [code, setCode] = useState(firstCode);
  const [outcome, setOutcome] = useState<Outcome | null>(
    initial ? { code: firstCode, data: initial } : null,
  );
  const [selection, setSelection] = useState<{ code: string; node: string } | null>(null);
  const loaded = outcome?.code === code;

  useEffect(() => {
    if (loaded) return;
    const controller = new AbortController();
    getNeighborhood(code, { depth: 2, signal: controller.signal }).then(
      (data) => setOutcome({ code, data }),
      (error: unknown) => {
        if ((error as { name?: string } | null)?.name === "AbortError") return;
        const apiError = error instanceof ApiError ? error : new ApiError(503, String(error));
        setOutcome({ code, error: apiError });
      },
    );
    return () => controller.abort();
  }, [code, loaded]);

  useEffect(() => {
    const onBack = () => {
      const previous = new URLSearchParams(window.location.search).get("code");
      setCode(previous || firstCode);
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, [firstCode]);

  const current = outcome?.code === code ? outcome : null;
  if (!current) {
    return <p className="type-body pt-6" role="status">Drawing the graph…</p>;
  }
  if ("error" in current) {
    const message = current.error.status === 404 ? NOT_IN_GRAPH : current.error.message;
    return (
      <div className="pt-6" role="status">
        <p className="type-body">{message}</p>
        <p className="type-body pt-3">
          <Link href={`/product/${code}`}>Open the product page</Link> or search for another
          product above.
        </p>
      </div>
    );
  }

  const data = current.data;
  const selected = selection?.code === code ? selection.node : data.center;
  const node = data.nodes.find((n) => n.id === selected) ?? data.nodes[0];
  const recenter = (nodeId: string) => {
    const next = productCode(nodeId);
    if (!next || next === code) return;
    window.history.pushState(null, "", `/graph?code=${next}`);
    setCode(next);
  };

  return (
    <div className="grid grid-cols-1 gap-6 pt-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0">
        <GraphKey data={data} />
        <GraphCanvas data={data} selected={selected} onSelect={(id) => setSelection({ code, node: id })} />
        <p className="type-small pt-2 text-ink-muted">
          {data.nodes.length} nodes{data.truncated ? ", the best-ranked shown where there are more" : ""}.
          Point at a mark to see its name. Select one to read about it; centre the graph on any
          product.
        </p>
      </div>
      <SelectedPanel
        node={node}
        isCenter={node.id === data.center}
        links={degree(data, node.id)}
        onRecenter={() => recenter(node.id)}
      />
      <details className="lg:col-span-2">
        <summary className="type-data-value cursor-pointer">Show the graph as a list</summary>
        <div className="grid grid-cols-1 gap-6 pt-3 sm:grid-cols-2 lg:grid-cols-3">
          {groupByKind(data).map(([kind, nodes]) => (
            <section key={kind} aria-label={KIND_NAMES[kind]}>
              <h3 className="type-data-label pb-1">
                {KIND_NAMES[kind]} ({nodes.length})
              </h3>
              <ul>
                {nodes.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      aria-pressed={n.id === selected}
                      onClick={() => setSelection({ code, node: n.id })}
                      className="type-small cursor-pointer py-1 text-left underline underline-offset-2"
                    >
                      {n.name}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </details>
    </div>
  );
}

const GRADE_TEXT: Record<NutriscoreGrade, string> = {
  a: "text-grade-a",
  b: "text-grade-b",
  c: "text-grade-c",
  d: "text-grade-d",
  e: "text-grade-e",
};

/** One of the graph's marks, drawn the way the canvas draws it. */
function Mark({ shape, className = "" }: { shape: NodeShape; className?: string }) {
  return (
    <svg viewBox="0 0 12 12" aria-hidden="true" className={`inline-block h-3 w-3 ${className}`}>
      {shape === "circle" && <circle cx="6" cy="6" r="5" fill="currentColor" />}
      {shape === "square" && <rect x="1" y="1" width="10" height="10" fill="currentColor" />}
      {shape === "diamond" && <path d="M6 0 12 6 6 12 0 6Z" fill="currentColor" />}
      {shape === "triangle" && <path d="M6 1 11.5 11H.5Z" fill="currentColor" />}
    </svg>
  );
}

/** What each mark in the graph is, with how many are shown (DESIGN.md, Graph explorer). */
function GraphKey({ data }: { data: GraphNeighborhood }) {
  const center = data.nodes.find((n) => n.id === data.center);
  const grade = center?.nutriscore_grade ?? null;
  return (
    <ul aria-label="Key" className="type-small flex flex-wrap gap-x-6 gap-y-1 pb-2">
      {center && (
        <li className="flex items-center gap-2">
          <Mark shape="circle" className={grade ? GRADE_TEXT[grade] : ""} />
          {grade ? "This product, in its Nutri-Score colour" : "This product"}
        </li>
      )}
      {keyEntries(data).map((entry) => (
        <li key={entry.kind} className="flex items-center gap-2">
          <Mark shape={entry.shape} className={entry.muted ? "text-ink-muted" : ""} />
          {KIND_NAMES[entry.kind]} ({entry.count})
        </li>
      ))}
    </ul>
  );
}

function SelectedPanel({
  node,
  isCenter,
  links,
  onRecenter,
}: {
  node: GraphNode;
  isCenter: boolean;
  links: number;
  onRecenter: () => void;
}) {
  const code = productCode(node.id);
  return (
    <Panel aria-label="Selected node" aria-live="polite" className="self-start">
      <p className="type-data-label pt-1">{isCenter ? "This product" : node.kind}</p>
      <h2 className="type-title pb-2 break-words">{node.name}</h2>
      <Rule weight="thin" />
      {node.kind === "Product" && (
        <div className="flex items-center gap-4 py-3">
          <span className="type-data-label">Nutri-Score</span>
          <GradeChip grade={node.nutriscore_grade ?? null} />
        </div>
      )}
      {node.detail && (
        <div className="type-body py-3">
          <p>{node.detail}</p>
          <p className="type-small pt-1 text-ink-muted">{AI_NOTE}</p>
        </div>
      )}
      {(node.kind === "Brand" || node.kind === "Category") && (
        <p className="type-body py-3">Linked to {links} of the products shown.</p>
      )}
      {code && (
        <p className="flex flex-wrap gap-x-6 gap-y-2 py-3">
          <Link href={`/product/${code}`} className="type-data-value">
            Open the product page
          </Link>
          {!isCenter && (
            <button type="button" onClick={onRecenter} className="type-data-value cursor-pointer underline">
              Centre the graph here
            </button>
          )}
        </p>
      )}
    </Panel>
  );
}
