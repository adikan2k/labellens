/** Interface wording from docs/DESIGN.md section 4. One place, so every page says it the same way. */

export const WAKING_UP = "Search is waking up. Try again in a few seconds.";
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
  { href: "/dashboard", title: "The dashboard", note: "The US packaged-food landscape" },
  { href: "/graph", title: "The food graph", note: "Products, brands and the ingredients they share" },
] as const;

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

/** The four numbers on the home page, each from an eval report in evals/results/. */
export const MEASURED = [
  { value: "0.98", label: "Fact score for the ask agent, against 0.26 for search alone", file: "evals/results/ask_agent.md" },
  { value: "98%", label: "Of nutrient values read right from real label photos", file: "evals/results/label_reading_claude-haiku-5-5.md" },
  { value: "29/30", label: "Requests where Claude picks the right LabelLens tool", file: "evals/results/mcp_tools.md" },
  { value: "184 ms", label: "Search, 95th percentile, on the live site", file: "evals/results/search_latency_public.md" },
] as const;

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
  sampleIntro: "Or try a sample label:",
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
export const ASK_AI_NOTE =
  "Answers are written by AI from Open Food Facts data. Check them against the sources.";
export const ASK_REFUSED_NOTE =
  "LabelLens doesn’t give medical or dietary advice. A doctor or registered dietitian can.";
export const ASK_REPLAY_NOTE = "Recorded example run. Live answers come back tomorrow (UTC).";
export const ASK_WAKING_UP = "The ask agent is waking up. Try again in a few seconds.";
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
export const MCP_URL = "https://labellens-api-1036759996795.us-east4.run.app/mcp";

/** The ask agent's public limits, from api/app/config.py. */
export const ASK_LIMITS = {
  perHour: 10,
  dailySpendUsd: 0.5,
  timeoutSeconds: 45,
};

export type EvalResult = {
  name: string;
  /** The number that matters, in a sentence a shopper can read. */
  headline: string;
  /** Path from the repository root; the About page links it on GitHub. */
  file: string;
};

/** Every eval in evals/results/, newest numbers as committed. Tests check each file exists. */
export const EVAL_RESULTS: EvalResult[] = [
  {
    name: "Ask agent",
    headline:
      "Fact score 0.98 on 43 answerable questions, against 0.26 for an explainer-only baseline. All 5 requests for advice refused.",
    file: "evals/results/ask_agent.md",
  },
  {
    name: "Category suggestions",
    headline:
      "90.0% of 200 products put in the right category (target 90%). The labels were written by an AI model, not a person.",
    file: "evals/results/category_accuracy_claude-haiku-5-5-full-silver.md",
  },
  {
    name: "Claude connector tool choice",
    headline: "Claude picked the right tool with the right arguments for 29 of 30 requests (target 90%).",
    file: "evals/results/mcp_tools.md",
  },
  {
    name: "Search speed",
    headline: "95% of searches answered within 193 ms on the public API (target 300 ms).",
    file: "evals/results/search_latency_public.md",
  },
  {
    name: "Graph and swaps speed",
    headline:
      "95% of graph neighbourhoods within 406 ms and swap lists within 233 ms on the public API (target 1 s).",
    file: "evals/results/graph_latency_public.md",
  },
  {
    name: "Page speed",
    headline: "Lighthouse performance 100 on home, 98 on a product page and 100 on the dashboard (target 90).",
    file: "evals/results/lighthouse.md",
  },
  {
    name: "Reading labels",
    headline:
      "98% of nutrient values read correctly from 30 real label photos (95–99%), checked against the photos; every value right on 85% of labels.",
    file: "evals/results/label_reading_claude-haiku-5-5.md",
  },
  {
    name: "Waking up",
    headline: "After an hour with no visitors, the first search took 22.6 s; the next ones about 0.1 s.",
    file: "evals/results/cold_start.md",
  },
];

/** A link to a file in the repository on GitHub. */
export function repoFileUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path}`;
}
