import type { Metadata } from "next";
import { Suspense } from "react";

import { GraphExplorer } from "@/components/graph/graph-explorer";
import { GraphSearch } from "@/components/graph/graph-search";
import type { GraphNeighborhood } from "@/lib/api";
import { cachedNeighborhood } from "@/lib/cached";

export const metadata: Metadata = { title: "Graph" };

// Shown when no product is chosen: a well-known product the graph holds.
const DEFAULT_CODE = "0016000275263";

/** Not async: the query is read inside the Suspense boundary, so the shell prerenders. */
export default function GraphPage({ searchParams }: PageProps<"/graph">) {
  return (
    <div className="w-full px-4 pt-8 pb-16">
      <h1 className="type-title">The food graph</h1>
      <p className="type-body max-w-measure pt-2 text-ink-muted">
        Products, the brands that make them, their categories, additives and ingredients, and the
        other products they share them with.
      </p>
      <div className="pt-6">
        <GraphSearch />
      </div>
      <Suspense fallback={<p className="type-body pt-6">Drawing the graph…</p>}>
        {searchParams.then(({ code }) => {
          const chosen = typeof code === "string" && code ? code : DEFAULT_CODE;
          // Keyed by product, so a search link to another product starts afresh.
          return <ExplorerWithData key={chosen} code={chosen} />;
        })}
      </Suspense>
    </div>
  );
}

/** Fetches the neighbourhood during the server render; on any failure the browser tries itself. */
async function ExplorerWithData({ code }: { code: string }) {
  let initial: GraphNeighborhood | null = null;
  try {
    initial = await cachedNeighborhood(code);
  } catch {
    initial = null;
  }
  return <GraphExplorer code={code} initial={initial} />;
}
