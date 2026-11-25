/** Interface wording from docs/DESIGN.md section 4. One place, so every page says it the same way. */

export const WAKING_UP = "Search is waking up. Try again in a few seconds.";
/** Shown while a search has been running this long: the API is starting after a quiet spell. */
export const SEARCH_SLOW_AFTER_MS = 2000;
export const SEARCH_SLOW =
  "Search is waking up after a quiet spell. The first one can take about 10 seconds; the rest are fast.";
export const NO_MATCH = "No products match. Try a brand name or scan the barcode number.";
export const AI_NOTE = "Written by AI from Open Food Facts data.";
export const AI_CATEGORY_NOTE =
  "Category suggested by AI from the product’s name and ingredients; Open Food Facts gives none.";
export const ATTRIBUTION = "Contains data from Open Food Facts, available under the Open Database License.";

/** "Open Food Facts has no sugar or fiber value for this product." */
export function missingValues(names: string[]): string | null {
  if (names.length === 0) return null;
  const list =
    names.length === 1
      ? names[0]
      : `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
  return `Open Food Facts has no ${list} value for this product.`;
}

export const SWAP_RULE =
  "Same category, a better Nutri-Score, and no additive that Open Food Facts flags for high overexposure risk.";
/** Ways into the site from home: the first three are tiles, the rest links. */
export const HOME_WAYS_IN = [
  { href: "/label", title: "Read a label", note: "Photograph any pack, even one LabelLens has never seen, and see it explained." },
  { href: "/ask", title: "Ask a question", note: "An AI agent looks it up in the data, step by step, and cites what it used." },
  { href: "/compare", title: "Compare two products", note: "Their labels side by side, per 100 g, with every difference." },
  { href: "/basket", title: "My basket", note: "Your products together, with better swaps" },
  { href: "/additives", title: "The additive guide", note: "What each additive is, and where it turns up" },
  { href: "/preferences", title: "My preferences", note: "Your own rules, checked on every product" },
  { href: "/dashboard", title: "The dashboard", note: "The US packaged-food landscape" },
  { href: "/graph", title: "The food graph", note: "Products, brands and the ingredients they share" },
] as const;

/** My basket (DESIGN.md, "My basket"). */
export const BASKET = {
  title: "My basket",
  intro:
    "The products you're thinking of buying, looked at together. It's kept in this browser only: no account, nothing sent anywhere but the barcodes LabelLens looks up.",
  add: "Add to my basket",
  added: "In my basket",
  remove: "Remove",
  swap: "Swap",
  emptyTitle: "Start your basket",
  emptyBody:
    "Add products from their pages: search for them, scan a barcode, or photograph a label. Then see them together and swap the worst ones.",
  full: (max: number) => `Your basket holds ${max} products at most. Remove one to add another.`,
  sharedTitle: "A shared basket",
  sharedNote: "Someone shared this basket with you. Saving it replaces yours.",
  save: "Save as my basket",
  share: "Share this basket",
  copied: "Link copied",
  additivesTitle: "Additives across the basket",
  noAdditives: "None of these products lists an additive.",
  gradeBarLabel: "Products by Nutri-Score",
  loading: "Looking up your products…",
  missing: (code: string) => `${code} is no longer in the data.`,
  swapLine: (name: string, reason: string) => `Better swap: ${name}. ${reason}.`,
} as const;

/** My preferences and the Your rules box (DESIGN.md, "My preferences"). */
export const PREFERENCES = {
  title: "My preferences",
  intro:
    "Your own rules, checked on every product page, label read, comparison and your basket. Set only the ones you want; LabelLens doesn't suggest values. They're kept in this browser only: no account, nothing sent anywhere.",
  limitsTitle: "Limits per 100 g",
  limitUnit: "g or less",
  limitsNote: "Leave a box empty for no limit.",
  gradeLabel: "Nutri-Score",
  gradeAny: "Any",
  gradeSuffix: "or better",
  ultraProcessed: "Not ultra-processed (NOVA 4)",
  additivesTitle: "Additives to avoid",
  findAdditive: "Find an additive to avoid",
  findPlaceholder: "Name or E number",
  avoid: "Avoid",
  remove: "Remove",
  noneAvoided: "No additives yet. Find one above, or open one from the additive guide.",
  additivesUnavailable: "The additive list is not available right now. Try again in a minute.",
  saved: "Saved in this browser.",
  nothingSet: "No rules set.",
  clear: "Clear my rules",
  boxTitle: "Your rules",
  edit: "Change your rules",
  prompt: "Set your own rules for sugars, salt, Nutri-Score, additives and more.",
  outcome: { meets: "Meets", misses: "Misses", unknown: "Not known" },
  basketMeets: (meets: number, count: number) => `${meets} of ${count} meet all your rules`,
  basketMisses: (shorts: string[]) => `Misses your rules: ${shorts.join(", ")}`,
  compareRow: "Your rules",
} as const;

/** The additive guide (DESIGN.md, "Additive guide"). */
export const ADDITIVES = {
  title: "Additives",
  intro: (count: number) =>
    `${count.toLocaleString("en-US")} additives turn up on US labels. Here is what each one is, what it does, and how often it is used, most common first.`,
  findLabel: "Find an additive",
  findPlaceholder: "Name or E number",
  flaggedOnly: "Flagged by Open Food Facts only",
  flagged: "Flagged by Open Food Facts",
  shown: (shown: number, total: number) =>
    shown === total ? `${total} additives` : `${shown} of ${total} additives`,
  none: "No additive matches. Try its E number, such as E330.",
  products: "US products list it",
  share: "of named US products",
  usedMostIn: "Used most in",
  noCategories: "Open Food Facts gives no category for the products that list it.",
  examples: "Products that list it",
  noExplainer: (fn: string | null) =>
    fn
      ? `Used as: ${fn.toLowerCase()}. LabelLens has no longer explainer for it yet.`
      : "Open Food Facts does not list what it is used for.",
  flaggedNote:
    "Open Food Facts rates this additive a high risk of overexposure: of people eating more than is considered acceptable. It is their flag, not a ban or a safety ruling.",
  facts:
    "Facts from Open Food Facts. The guide says what an additive is and where it is used, not whether to eat it.",
  more: (name: string) => `More about ${name}`,
  notFoundTitle: "No such additive",
  notFoundBody: "This snapshot has no additive at that address.",
  unavailable: "The additive guide is not ready. Try again in a few seconds.",
} as const;

/** The graph page's three columns (DESIGN.md, Graph explorer). */
export const GRAPH = {
  centre: "This product",
  hubs: "What it is linked to",
  peers: "Products that share them",
  peersTop: "Most in common",
  peersOf: (name: string) => `Others with ${name}`,
  noPeers: "No other product here shares it.",
  inCommon: "in common",
  caption:
    "Lines join things that are linked. Products are ranked by what they share, with rarer things counting for more, so sharing salt counts for little. The number beside a product is how many things it shares. A product listed under several barcodes is shown once.",
  sharedWith: (name: string) => `In common with ${name}`,
  hubLinks: (others: number) =>
    others === 0
      ? "Of the products shown, only this one is linked to it."
      : `This product and ${others} of the others shown are linked to it.`,
  widerCategory: "A wider category. This product is in it through a narrower one.",
  nothingShared: "It shares nothing in the middle column directly.",
} as const;

/** The home page's live label. */
export const SPECIMEN = {
  label: "A real label from the data",
  caption: "A real product's label and barcode. Scan it from your phone.",
  next: "Next label",
} as const;

/** The home page's bands (DESIGN.md, Home). */
export const SHELF = {
  tickerLabel: "What the data says",
  pause: "Pause",
  play: "Play",
  title: "The shelf, graded",
  caption: (total: string) =>
    `Every one of the ${total} US products with a Nutri-Score, sized by how many get each grade.`,
  listLabel: "Products by Nutri-Score",
  link: "See the dashboard",
  waysTitle: "More ways in",
  measuredTitle: "How it’s measured",
  measuredCaption:
    "Every claim on this site has an eval behind it, with error bars, and every report lists its misses.",
  report: "Read the report",
} as const;

/** The /label page: reading a food label from a photo. */
export const LABEL = {
  intro:
    "Photograph the ingredients, the nutrition panel, or both. LabelLens reads the label with AI and explains it from its data on a million US products.",
  addPhoto: "Add a photo",
  addAnother: "Add another photo",
  read: "Read the label",
  reading: "Reading the label…",
  remove: "Remove",
  privacy:
    "Photos go to Anthropic to be read and are not kept by LabelLens. What was read is kept in our trace log (Langfuse), which does not delete it on its free plan.",
  readByAi: "Read by AI from your photo. Check it against the pack.",
  notALabel:
    "That doesn't look like a food label. Try a photo of the ingredients or the nutrition panel.",
  looksLike: "Looks like this product in our data",
  noMatch: "Not found in the US data",
  unmatchedAdditives: (names: string[]) =>
    `Also on the label, with no entry in LabelLens: ${names.join(", ")}.`,
  swapsHeading: "Better swaps",
  categoryHeading: (category: string | null) =>
    `Well-graded products in ${category ? category.toLowerCase() : "this category"}`,
  categoryNote:
    "Products in the same category with Nutri-Score A or B and no additive Open Food Facts flags. The photo matched no product, so these are not swaps for it.",
  barcodeMissing: (code: string) => `The barcode ${code} isn't in the US data.`,
  sampleIntro: "Or try a sample label",
  sampleAction: "See it read",
  sampleNote: "Recorded example: this sample was read once and saved, so it costs nothing to show.",
  sampleCredit: "Sample photos: Open Food Facts contributors, CC BY-SA.",
  unavailable: "The label reader is not available right now. Try again later.",
  tooMany: "Two photos at most: the ingredients and the nutrition panel.",
} as const;

export const SCAN = {
  button: "Scan a barcode",
  pointing: "Point the camera at the barcode. The picture stays on this device.",
  starting: "Starting the camera…",
  blocked:
    "Camera access is blocked. Allow it in your browser's settings, or type the barcode instead.",
  noCamera: "No camera was found. Type the barcode instead.",
  readerFailed: "The barcode reader didn't load. Type the barcode instead.",
  lookingUp: (code: string) => `Looking up ${code}…`,
  missing: (code: string) => `${code} isn't in the US snapshot.`,
  addIt: "Add it to Open Food Facts",
  photographInstead: "Photograph its label instead",
  orPhotograph: "or photograph the label",
} as const;
export const COMPARE_INTRO =
  "Two products' labels side by side, per 100 g. Differences are the second against the first.";
export const COMPARE_WITH = "Compare with another product";
export const SWAPS_UNAVAILABLE ="Swaps are not available right now. Try again in a minute.";

/** Why a product has no swaps, from what the swap rule needs. */
export function noSwapsReason(product: {
  nutriscore_grade: string | null;
  category_main: string | null;
}): string {
  if (!product.category_main || product.category_main === "other") {
    return "This product has no category to compare within.";
  }
  if (!product.nutriscore_grade) {
    return "Open Food Facts has no Nutri-Score for this product, so there is nothing to compare.";
  }
  if (product.nutriscore_grade === "a") {
    return "It already scores Nutri-Score A, so nothing in its category scores better.";
  }
  return "No similar product in this category scores better without a flagged additive.";
}

export const ASK_EXAMPLES = [
  "Breakfast cereals under 5 g sugar without artificial colours",
  "Healthier swaps for Nacho Cheese Doritos",
  "What is carrageenan and why is it in yogurt?",
];
/** What the agent does for each example, shown under it (DESIGN.md, Ask). */
export const ASK_EXAMPLE_NOTES: Record<(typeof ASK_EXAMPLES)[number], string> = {
  "Breakfast cereals under 5 g sugar without artificial colours":
    "Writes its own SQL over the product tables and cites every row it used.",
  "Healthier swaps for Nacho Cheese Doritos":
    "Finds better-graded products in the same category, with the reason for each.",
  "What is carrageenan and why is it in yogurt?":
    "Searches the additive explainers, then counts the yogurts that list it.",
};
export const ASK_EXAMPLES_TITLE = "Or try one of these";
export const ASK_AI_NOTE =
  "Answers are written by AI from Open Food Facts data. Check them against the sources.";
export const ASK_REFUSED_NOTE =
  "LabelLens doesn’t give medical or dietary advice. A doctor or registered dietitian can.";
export const ASK_REPLAY_NOTE = "Recorded example run. Live answers come back tomorrow (UTC).";
export const ASK_WAKING_UP = "The ask agent is waking up. Try again in a few seconds.";
/** Shown when no step has arrived this long after asking: the agent is loading on a new instance. */
export const ASK_SLOW_AFTER_MS = 5000;
export const ASK_SLOW =
  "The agent is starting up after a quiet spell. The first question can take about 20 seconds; the next ones take about 4.";
export const ASK_UNAVAILABLE = "The ask agent is not available right now. Try again later.";

/** "Try again in about 12 minutes." from a Retry-After in seconds. */
export function retryIn(seconds: number | null): string {
  if (!seconds) return "Try again later.";
  const minutes = Math.max(1, Math.round(seconds / 60));
  return `Try again in about ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}

/** One line under the ask box; the About page's "What happens to your questions" says more. */
export const ASK_PRIVACY_NOTE =
  "Questions go to Anthropic and Voyage AI to answer them and are kept in our trace log (Langfuse), which does not delete them on its free plan. Don’t include personal details.";

export const REPO_URL = "https://github.com/adikan2k/labellens";

/** Who built it: the footer credit and the "How it's built" page. */
export const AUTHOR = {
  name: "Aditya Kanbargi",
  linkedin: "https://www.linkedin.com/in/adikan2k/",
  github: "https://github.com/adikan2k",
} as const;
export const BUILT_HREF = "/how-its-built";
export const BUILT_LABEL = "How it’s built";
export const MCP_URL = "https://labellens-api-1036759996795.us-east4.run.app/mcp";

/** The ask agent's public limits, from api/app/config.py. */
export const ASK_LIMITS = {
  perHour: 10,
  dailySpendUsd: 0.5,
  timeoutSeconds: 45,
};

/** The "How it's built" page: for someone who wants to know how the site works. */
export const BUILT = {
  description:
    "How LabelLens is built: the data pipeline, the knowledge graph, the AI agent and its evals, the stack and what it costs.",
  facts: [
    { value: "1M", label: "US products through the pipeline" },
    { value: "94", label: "data tests on every build" },
    { value: "9", label: "evals, each with a published report" },
    { value: "~$6", label: "model spend for the whole project" },
  ],
  steps: [
    {
      name: "Data",
      text: "The US subset of the Open Food Facts export goes through staging, intermediate and mart models in dbt, with tests on every key, range and relationship. Duplicate barcodes and impossible nutrient values are handled there, once.",
    },
    {
      name: "Enrichment",
      text: "Claude fills in a category for the products that Open Food Facts’ tags leave unplaced, and writes an explainer for each additive and common ingredient. It runs through the Batch API and its outputs are committed, so a rerun costs nothing.",
    },
    {
      name: "Serving",
      text: "Postgres holds the serving tables, swapped in atomically on each load, with full-text search and pgvector for explainer search. Neo4j holds a subset of the products as a graph, capped to fit the free tier.",
    },
    {
      name: "Apps",
      text: "One FastAPI service serves the website, the ask agent and the MCP server. The API’s schema is checked against a written OpenAPI contract, and the web’s types are generated from the same file.",
    },
    {
      name: "Operations",
      text: "GitHub Actions runs every check on each pull request, deploys the API on merge without stored keys, smoke-tests production every 6 hours, and reruns the connector eval when its tools change.",
    },
  ],
  stack: [
    { layer: "Data", tools: "DuckDB, dbt, Dagster, Python (uv, Ruff, Pyright, pytest)" },
    {
      layer: "AI",
      tools:
        "Claude Haiku for the agent, enrichment and label reading; Claude Sonnet as eval judge; Voyage AI embeddings; Langfuse tracing",
    },
    { layer: "Storage", tools: "Neon Postgres with pgvector, Neo4j AuraDB" },
    { layer: "API", tools: "FastAPI on Google Cloud Run, with the MCP server mounted at /mcp" },
    { layer: "Web", tools: "Next.js 16, React, Tailwind CSS v4, Vitest, on Vercel" },
  ],
  caveats: [
    "The category labels came from a larger AI model, not from a person, so that result compares two models.",
    "I wrote both the ask eval’s questions and the agent’s prompt.",
    "The samples are small, so each report gives a range. Read it before comparing two numbers.",
  ],
  notes: [
    {
      title: "The agent’s SQL is safe because of the database, not a parser",
      text: "The agent writes its own SQL, but runs it as a role that can read five tables and nothing else, in a read-only transaction with a 3-second timeout and a 50-row cap. Only rows a tool actually returned can be cited, so an invented source is dropped.",
    },
    {
      title: "The eval caught a regression the demo hid",
      text: "Telling the agent to list each product once also made it de-duplicate counts: 1,178 cereals instead of 1,323, and the fact score fell to 0.88. The fix was scoped to lists, and the score went back to 0.98.",
    },
    {
      title: "Only 1 of 11 production runs reached the trace log",
      text: "Cloud Run samples a few requests for its own tracing, and OpenTelemetry’s default sampler followed that decision, so the rest were silently dropped. Each run now starts a trace of its own.",
    },
    {
      title: "“Healthier swaps” offered restaurant menus",
      text: "Open Food Facts lists menu items under 16- to 24-digit codes, and 34,200 of them qualified as swaps. A barcode check-digit test now keeps swaps to real packaged products.",
    },
    {
      title: "Prompt caching was measured before it was trusted",
      text: "Caching the fixed prompt and tools made a run 64% cheaper across 10 questions, with the same answers.",
    },
  ],
  cost: [
    "Model calls: about $6 for the whole project. $5.18 of that was the one-off category fill, 604,507 inputs through the Batch API.",
    "Evals are cached, so rerunning one costs $0. A paid run prints an estimate first and only sends when confirmed.",
    "Hosting runs on free tiers: Neon, AuraDB, Cloud Run, Vercel, Langfuse and Voyage AI.",
    "The public ask agent is limited to 10 questions an hour per visitor and $0.50 a day overall. Past that it shows recorded runs.",
  ],
  rules: [
    "Every feature ships with a test or an eval.",
    "No paid model call runs without a limit and a printed cost estimate.",
    "The interface uses only the tokens in the design system.",
    "Every interface change is checked with screenshots at phone, laptop and wide-screen widths.",
  ],
} as const;

/** The measured numbers live in measured.ts, written once and checked against their reports. */
export { EVAL_RESULTS, MEASURED, type EvalResult } from "./measured";

/** A link to a file in the repository on GitHub. */
export function repoFileUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path}`;
}
