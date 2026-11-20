/**
 * The architecture as label panels, top to bottom: each stage is a row of panels, and data
 * flows down the page. It is a list, so it reads in order without the picture.
 */

export type Part = { name: string; detail: string };
export type Stage = { stage: string; note: string; parts: Part[] };

export const STAGES: Stage[] = [
  {
    stage: "Source",
    note: "One bulk file, never the live API.",
    parts: [
      { name: "Open Food Facts export", detail: "food.parquet, 8 GB, every product in the world" },
    ],
  },
  {
    stage: "Pipeline",
    note: "Runs in Dagster; everything is rebuilt from the snapshot.",
    parts: [
      { name: "Ingest", detail: "A dated snapshot, resumable, never edited" },
      { name: "dbt on DuckDB", detail: "Staging, intermediate and mart models with 94 data tests" },
      { name: "Enrichment", detail: "Claude Haiku on the Batch API: categories and explainers, cached" },
    ],
  },
  {
    stage: "Storage",
    note: "Postgres tables are swapped in whole on each load.",
    parts: [
      { name: "Neon Postgres", detail: "Serving tables, full-text search, pgvector for explainers" },
      { name: "Neo4j AuraDB", detail: "Products, brands, categories, additives and ingredients" },
    ],
  },
  {
    stage: "API",
    note: "One service for every client.",
    parts: [
      { name: "FastAPI on Cloud Run", detail: "Typed endpoints from an OpenAPI contract, deployed on merge" },
    ],
  },
  {
    stage: "Apps",
    note: "Three ways to use the same data.",
    parts: [
      { name: "Website", detail: "Next.js on Vercel: search, labels, compare, basket, dashboard, graph" },
      { name: "Ask agent", detail: "Claude with SQL, graph and search tools; traced in Langfuse" },
      { name: "Claude connector", detail: "An MCP App: four tools and a label card inside Claude" },
    ],
  },
];

const COLUMNS: Record<number, string> = {
  1: "",
  2: "sm:grid-cols-2",
  3: "sm:grid-cols-3",
};

export function Architecture() {
  return (
    <ol aria-label="Architecture, from the source data to the apps">
      {STAGES.map((stage, i) => (
        <li key={stage.stage}>
          {i > 0 && (
            <p aria-hidden="true" className="type-heading py-2 text-center">
              ↓
            </p>
          )}
          <div className="grid gap-x-6 gap-y-2 md:grid-cols-[12rem_1fr]">
            <div>
              <h3 className="type-data-label">{stage.stage}</h3>
              <p className="type-small text-ink-muted">{stage.note}</p>
            </div>
            <ul className={`grid grid-cols-1 gap-3 ${COLUMNS[stage.parts.length]}`}>
              {stage.parts.map((part) => (
                <li key={part.name} className="panel px-3 py-2">
                  <span className="type-data-value block">{part.name}</span>
                  <span className="type-small block text-ink-muted">{part.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </li>
      ))}
    </ol>
  );
}
