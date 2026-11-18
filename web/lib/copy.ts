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
export const SWAPS_UNAVAILABLE = "Swaps are not available right now. Try again in a minute.";

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
    name: "Waking up",
    headline: "After an hour with no visitors, the first search took 22.6 s; the next ones about 0.1 s.",
    file: "evals/results/cold_start.md",
  },
];

/** A link to a file in the repository on GitHub. */
export function repoFileUrl(path: string): string {
  return `${REPO_URL}/blob/main/${path}`;
}
