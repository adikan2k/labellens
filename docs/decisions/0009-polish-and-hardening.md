# 0009: Polish and hardening (phase 7)

Status: accepted. Date: 2026-11-18. Phase 7.

Phase 7 followed a review of everything built so far. The engineering was strong, but the presentation was weak, and a few problems were visible to users. It ran as five parallel pieces of work (PRs #10–#14): data, website, operations, prompt caching and eval intervals. Human category labels were left out by choice.

## Data people could see

**Swaps need a real barcode.**
- **Chosen:** a GS1 check-digit test (GTIN-8, -12, -13 or -14) gives a `gtin_valid` column, and only the swap candidates use it.
- **Why:**
  - 34,200 restaurant menu items and shop-weighed goods (16–24 digit codes) qualified as "healthier swaps"; Doritos was offered Quiznos.
  - Those products are still real label data, so search, product pages and counts keep them.
- **Rejected:** dropping the 70,042 invalid codes from the dataset. That would hide products people do look up and would change every count the evals rest on.

**Names print the way labels do.**
- **Chosen:** a word-level rule:
  - a letter followed by digits takes a capital (B12, E150a);
  - a variant letter after a word like vitamin, acesulfame or blue is capitalised (Vitamin E, Acesulfame K, Patent blue V);
  - a short acronym list is upper-cased (DHA, MSG).
- **Rejected:** title case, which would wreck "Mono- and diglycerides of fatty acids".

**More category tags, but only specific ones.**
- **Chosen:** `en:bacon` and seven other specific tags, each where the AI's category already agreed 72–98% of the time. This moved 258 bacon products from fresh meat to "Deli meats, sausages and bacon" and 1,936 products onto their own tags.
- **Rejected:** mapping umbrella tags like `en:snacks` and `en:beverages` (about 90,000 products). The AI's category beats them.

**One listing per product in search.**
- **Chosen:** fetch four times the limit through the existing rank index and keep the first row per name and brand. Local p95 was 77 ms, and production p95 stayed at 184 ms.
- **Rejected:** `distinct on` over every match, which sorts all matches for broad queries like "milk".

**Truth facts moved with the data.** The category change shifted six of the ask eval's counts. Only those six questions were rerun ($0.03), and the agent still scored 0.98 against 0.26.

## Website

**Real 404s.**
- **Chosen:** a request check in `web/proxy.ts`. It asks the API whether the barcode exists, remembers hits, and rewrites unknown barcodes to a static not-found route that returns 404. It falls through if the API is slow or asleep.
- **Why:** with Cache Components, the prerendered shell sends 200 before any check inside the page runs, even one placed ahead of the Suspense boundary (Next 16 docs, "Status codes").
- **Rejected:** moving the lookup ahead of Suspense (it doesn't change the status), and turning off Cache Components (it would lose the fast shell).

**Titles:** a root `title.template`, and product titles of the form "Lucky Charms (Lucky Charms) · LabelLens".

**Privacy, stated as it is.**
- A line under the question box says questions go to Anthropic, Voyage AI and Langfuse, and that Langfuse's free plan doesn't delete them.
- **Why that wording:** Langfuse Hobby only limits how long data can be viewed (30 days); deletion policies need a paid plan. So the site promises no deletion.
- About gained four sections: the agent, using LabelLens in Claude, how each part is measured, and what happens to questions.
- It also corrected an old claim that the category labels were made by hand.

**The design pass.**
- **Method:** a script walked every element of every page against DESIGN.md's tokens and type roles.
- **Fixes:**
  - the search box's blue clear button;
  - an ingredient list narrower than its neighbours;
  - truncated names (text now wraps, and a test keeps `truncate` out);
  - dashboard label width;
  - table headers off the type scale;
  - a view transition that ignored reduced motion.
- **The graph page, decided afterwards:**
  - **Layout:** the title, intro and search moved onto the page width, so their left edge meets the header's; the graph itself stays full width, as DESIGN.md says. **Rejected:** putting the whole page on the page width, which would narrow the graph from about 1,210 to 780 px at 1600 px wide, for the sake of one edge.
  - **Labels:** Sigma's label grid only caps labels per grid cell, so long names in neighbouring cells ran into each other. Labels are now picked by a greedy collision check after every camera move: most-linked first, each kept only if it clears every kept label, covers no other dot and fits in the canvas. Measured on the Cheerios graph: 43 of 79 labels at the start, 7 zoomed out and all 79 zoomed in, with no overlaps in any of them. **Rejected:** a bigger label grid, which shows fewer labels and still lets neighbouring cells collide.

## Operations

**Production smoke test.**
- `scripts/smoke.py` makes 16 read-only checks: the API, MCP, every page, a real 404, and a 422 from `/ask` that costs nothing.
- It runs every 6 hours and as the last step of each deploy. It runs as a step of the deploy, not a separate workflow, so a failed check turns that deploy red.

**Deploy on merge, keyless.**
- **Chosen:** Workload Identity Federation, limited to this repo's `main` branch. The deploy account's roles are narrowed to single resources where possible.
- **Rejected:** a service-account key in GitHub secrets, which is long-lived and leaks.
- **Live:** after the one-time setup (`scripts/setup_ci_deploy.py --yes`), merging PR #16 built and deployed revision `labellens-api-00017`, and the smoke test after it passed 16/16.
- **One snag:** the first two runs failed with "forbidden from accessing the bucket", even though the account had full access to that bucket. When `gcloud builds submit` uses its default staging bucket, it first checks the bucket belongs to the project by listing every bucket in it, which needs project-wide `storage.buckets.list`. Naming the bucket (`--gcs-source-staging-dir`) skips that check.
  - **Rejected:** granting the project-wide listing. It would have fixed the error by widening the very access the setup was built to narrow.

**Weekly pipeline as a canary.**
- **Chosen:** every week CI downloads the export, builds and tests it, dry-runs both loads against their caps, and uploads the report. Publishing is manual.
- **Why:** new data invalidates the AI enrichment and every eval's expected facts, so a refresh should be a deliberate release.
- **Disk:** toolchains are removed and the parquet is deleted after the first model. On today's runner this turned out to be headroom, not a necessity.
- **First run:** green in 4 minutes.

**Test isolation.**
- **Problem:** the parallel sessions shared one local Postgres, and its roles belong to the whole cluster. Every test run re-passworded `labellens_readonly`, which broke every other run.
- **Fix:** each run creates `labellens_readonly_t<random>`, points the loader's grants at it, and drops it afterwards.

## Prompt caching, measured

- **Result:**
  - one cache marker on the system prompt caches the tools and prompt together (3,344 tokens);
  - across 10 questions, a run cost 64% less;
  - priced as if every run were cold, the saving would be 26%;
  - answers were equivalent.
- **Accounting fix:** cache reads are now priced at 0.1× the input price and cache writes at 1.25×. Before, every cached token was charged at the full input price.

## Error margins

Every eval report now gives 95% Wilson intervals, and the fact score gets a bootstrap interval over questions with a fixed seed. Reports were regenerated from cache at $0, and no point estimate changed. "97% on 30" now reads as 83–99%.

## Cold start, after an hour idle

After 67 minutes with no requests, the first search took 22.6 s, then 0.1 s. After 25 minutes it had taken 3.9 s, so the shorter wait was not representative.
- **Where the time went:** 6.3 s for Cloud Run to start an instance, 16.0 s in the app's startup step, and 0.2 s for the search with Neon waking. Neon was never the problem.
- **Likely cause:** startup imports the ask agent's libraries (`anthropic`, `langfuse` with OpenTelemetry), which a search never needs. Locally they take 3.5 s warm, and a fresh Cloud Run host reads the image's files on demand. The startup step logs no timings, so this is not yet proven.

- **Fix (PR #19):** the ask service is built on the first `/ask`. On revision 00018 the startup step took 0.41 s, against 4.6 s and 16.0 s on revision 00017's starts from zero.
- **Rejected:** a minimum of one instance, which removes cold starts but bills every hour. Kept as the fallback.

## Still open

- Time a full hour-idle cold start on revision 00018. The expected figure is about 7 s (instance start and app import, 6.3 s, are unchanged).
