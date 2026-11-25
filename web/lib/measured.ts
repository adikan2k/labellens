/**
 * Every measured number the site prints, written once. Each one names the eval report it comes
 * from and the exact text that report prints it as; measured.test.ts opens the report and fails
 * when that text is gone, so a rerun that changes a number can't leave the site behind.
 * The home page, About and "How it's built" all read from here.
 */

export type Measure = {
  /** As the site prints it. */
  value: string;
  /** The report, from the repository root. */
  file: string;
  /** What the report itself prints. */
  evidence: string;
};

const ASK = "evals/results/ask_agent.md";
const LABEL = "evals/results/label_reading_claude-haiku-5-5.md";
const MCP = "evals/results/mcp_tools.md";
const CATEGORY = "evals/results/category_accuracy_claude-haiku-5-5-full-silver.md";
const SEARCH = "evals/results/search_latency_public.md";
const GRAPH = "evals/results/graph_latency_public.md";
const LIGHTHOUSE = "evals/results/lighthouse.md";
const COLD = "evals/results/cold_start.md";
const CACHING = "evals/results/ask_caching.md";
const RETRIEVAL = "evals/results/retrieval.md";

export const M = {
  askFact: { value: "0.98", file: ASK, evidence: "0.98 (0.93–1.00)" },
  askBaseline: { value: "0.26", file: ASK, evidence: "0.26 (0.14–0.40)" },
  labelValues: { value: "98%", file: LABEL, evidence: "98% (95–99%) of 159" },
  labelWhole: { value: "85%", file: LABEL, evidence: "85% (68–94%) of 27" },
  mcpTools: { value: "29/30", file: MCP, evidence: "29/30: 97% (83–99%)" },
  category: { value: "90.0%", file: CATEGORY, evidence: "180/200: 90.0% (85.1–93.4%)" },
  searchP95: { value: "175 ms", file: SEARCH, evidence: "| **p95** | **175.0** |" },
  graphP95: { value: "406 ms", file: GRAPH, evidence: "**406.0**" },
  swapsP95: { value: "233 ms", file: GRAPH, evidence: "**233.2**" },
  lighthouseHome: { value: "100", file: LIGHTHOUSE, evidence: "| Home | 100 |" },
  lighthouseProduct: { value: "90", file: LIGHTHOUSE, evidence: "| Product | 90 |" },
  lighthouseDashboard: { value: "100", file: LIGHTHOUSE, evidence: "| Dashboard | 100 |" },
  coldBefore: { value: "22.6 s", file: COLD, evidence: "22.64 s" },
  coldLow: { value: "7 s", file: COLD, evidence: "| 7.07 s |" },
  coldHigh: { value: "10 s", file: COLD, evidence: "| 10.07 s |" },
  warmPing: { value: "5 minutes", file: COLD, evidence: "a ping every 5 minutes" },
  cachingSaving: { value: "64%", file: CACHING, evidence: "| -64% |" },
  retrievalTop5: { value: "98%", file: RETRIEVAL, evidence: "| Right explainer in the top 5 | 98% (93–99%)" },
  retrievalVectorAlone: { value: "74%", file: RETRIEVAL, evidence: "| 98% (93–99%) | 74% (66–81%)" },
  retrievalKeyword: { value: "58%", file: RETRIEVAL, evidence: "| 74% (66–81%) | 58% (50–67%)" },
  retrievalENumbersBefore: { value: "3%", file: RETRIEVAL, evidence: "| E-number | 30 | 100% (89–100%) | 3% (1–17%)" },
} as const satisfies Record<string, Measure>;

/** The four numbers on the home page, each linked to its report. */
export const MEASURED = [
  {
    value: M.askFact.value,
    label: `Fact score for the ask agent, against ${M.askBaseline.value} for search alone`,
    file: M.askFact.file,
  },
  {
    value: M.labelValues.value,
    label: "Of nutrient values read right from real label photos",
    file: M.labelValues.file,
  },
  {
    value: M.mcpTools.value,
    label: "Requests where Claude picks the right LabelLens tool",
    file: M.mcpTools.file,
  },
  {
    value: M.searchP95.value,
    label: "Search, 95th percentile, on the live site",
    file: M.searchP95.file,
  },
] as const;

export type EvalResult = {
  name: string;
  /** The number that matters, in a sentence a shopper can read. */
  headline: string;
  /** Path from the repository root; the pages link it on GitHub. */
  file: string;
};

/** Every eval in evals/results/, newest numbers as committed. */
export const EVAL_RESULTS: EvalResult[] = [
  {
    name: "Ask agent",
    headline: `Fact score ${M.askFact.value} on 43 answerable questions, against ${M.askBaseline.value} for an explainer-only baseline. All 5 requests for advice refused.`,
    file: ASK,
  },
  {
    name: "Explainer search",
    headline: `The ask agent's search puts the right explainer in its top 5 for ${M.retrievalTop5.value} of 125 questions. Vector search alone managed ${M.retrievalVectorAlone.value}: it found ${M.retrievalENumbersBefore.value} of E-numbers, which are now looked up exactly. Keyword search: ${M.retrievalKeyword.value}.`,
    file: RETRIEVAL,
  },
  {
    name: "Category suggestions",
    headline: `${M.category.value} of 200 products put in the right category (target 90%). The labels were written by an AI model, not a person.`,
    file: CATEGORY,
  },
  {
    name: "Claude connector tool choice",
    headline:
      "Claude picked the right tool with the right arguments for 29 of 30 requests (target 90%).",
    file: MCP,
  },
  {
    name: "Search speed",
    headline: `95% of searches answered within ${M.searchP95.value} on the public API (target 300 ms).`,
    file: SEARCH,
  },
  {
    name: "Graph and swaps speed",
    headline: `95% of graph neighbourhoods within ${M.graphP95.value} and swap lists within ${M.swapsP95.value} on the public API (target 1 s).`,
    file: GRAPH,
  },
  {
    name: "Page speed",
    headline: `Lighthouse performance ${M.lighthouseHome.value} on home, ${M.lighthouseProduct.value} on a product page and ${M.lighthouseDashboard.value} on the dashboard (target 90).`,
    file: LIGHTHOUSE,
  },
  {
    name: "Reading labels",
    headline: `${M.labelValues.value} of nutrient values read correctly from 30 real label photos (95–99%), checked against the photos; every value right on ${M.labelWhole.value} of labels.`,
    file: LABEL,
  },
  {
    name: "Waking up",
    headline: `After a quiet spell, the first request takes ${M.coldLow.value.replace(" s", "")} to ${M.coldHigh.value} while the API starts (it was ${M.coldBefore.value}); the next ones take under 0.1 s. A ping every ${M.warmPing.value} now keeps it awake most of the time.`,
    file: COLD,
  },
];
