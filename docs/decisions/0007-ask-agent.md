# 0007: The ask agent (phase 5)

Status: draft for Aditya to rewrite. Date: 2026-11-18. Phase 5.

## A hand-written loop, not a framework

**Chosen:** a manual tool-use loop on the Anthropic SDK (`api/app/ask/agent.py`, about 300 lines). Haiku 5.5 with thinking off; at most 6 tool calls, then `tool_choice: none` so the model has to answer.
**Why:**
- Every step is ours to stream: a `step` event goes out as each tool call finishes.
- The limits (calls, a 45 s wall clock, a timeout on each model call) are a few lines each and are tested with a scripted fake client.
- One dependency fewer to keep current.
**Rejected:**
- The SDK's tool runner: it hides the steps we stream.
- Agent frameworks: more surface than three tools need.

## Three tools, each as narrow as it can be

**Chosen:**
- **`query_sql`:** free SQL, but only through a role that can read five tables and nothing else. Each query runs inside `BEGIN READ ONLY` with a 3 s statement timeout and is wrapped in `LIMIT 51`.
- **`query_graph`:** four fixed Cypher templates with parameters. No free-form Cypher.
- **`search_explainers`:** pgvector cosine search over 1,019 explainers embedded with Voyage `voyage-4-lite`. Exact search: at this size an index buys nothing.

**Why:**
- SQL is where the questions are (filters, counts, comparisons), and it's hard to template.
- The role makes free SQL safe where it matters, in the database, not in a parser. On Neon it can read products and explainers, can't read `meta`, `stats` or the run log, can't write, and gets cut off at 3 s.
- The role is created with SQL, not in Neon's console, because console roles join `neon_superuser`.
- Cypher has no equivalent of a read-only role on AuraDB Free, so the graph gets templates.

## Citations can't be invented

**Chosen:** every row, node and explainer a tool returns gets an id (`R3`, `N1`, `E2`). The model cites with those ids. The server numbers them and links them (rows to product pages, nodes to the explorer) and drops any id no tool returned.
**Why:** a citation in an answer is then always something the agent actually looked at.

## Advice is refused, by the model, with a marker

**Chosen:** the prompt defines advice (whether a food is safe or right for someone's condition, allergy, pregnancy, child or diet; what to eat; diagnosis). Such questions start with `[refused]`, and the server turns that into `refused: true`, which the page shows with its own note. Out-of-scope questions get a plain decline without the marker.
**Why:** the line between "which yogurts have no added sugar" (fine) and "is this yogurt OK for my diabetes" (advice) is semantic, and a keyword filter would get both wrong.
**Result:** 5/5 advice requests refused, 0 false refusals (the baseline, with the same prompt, refused 3 answerable questions).

## Public limits that hold across instances

**Chosen:**
- An `app.ask_runs` table in a schema the loader never swaps. It records time, a keyed hash of the client address (never the address itself), tokens, cost and outcome.
- 10 questions per client per hour, checked before the stream opens (429 with `Retry-After`).
- A $0.50 daily cap. Past it, the closest of three recorded runs is served, labelled as a replay.

**Why:** Cloud Run can run two instances, so limits held in memory would double. The table also makes cost per run something we can query.

## The eval: computed truth, a baseline, and a judge

**Chosen:**
- 50 questions: 25 SQL, 8 graph, 10 explainer, 5 advice and 2 out of scope.
- Each expected fact is computed by a truth query kept in the dataset, so the facts move with the data, not with my memory of it.
- The agent is compared with a baseline that has only `search_explainers` (the retrieval-only design).
- Sonnet 5.5 judges each fact as supported or not, with structured output.

**Result (`ask-v2`):**

| | Agent | Baseline |
| --- | --- | --- |
| Fact score | 0.98 | 0.26 |
| Fully correct | 42/43 | 11/43 |
| Expected tool | 43/43 | 10/43 |
| Cost, 50 questions | $0.044 | $0.015 |
| p50 / p95 latency | 2.5 s / 4.6 s | 1.3 s / 2.7 s |

Explainer questions score 1.00 for both, as they should. The gap is all SQL and graph.

**What the first run taught (`ask-v1`, 0.88):**
- The replays listed one product twice (separate barcodes, same name). A prompt rule alone didn't hold from run to run. What held was showing `distinct on (name, brand)` in the tool's example query.
- That fix then leaked into counts: four count questions came back de-duplicated (1,178 cereals against 1,323). `ask-v2` keeps de-duplication for lists and `count(*)` for counts, because LabelLens counts listings everywhere.
- Two truth queries were wrong: Lucky Charms' nearest neighbour was another Lucky Charms listing. They now skip other listings of the same product.

**Still missed:** "Which well-known cereals contain tocopherols?" The agent names Cheerios; the truth takes the graph's top three by rank (granolas). The question is ambiguous; I left it as a miss rather than tune it until it passes.

## Tracing

Langfuse Cloud (Hobby): a trace per run, a generation per model call with tokens and cost, a span per tool call. It is off without keys and never fails a run.

**What the first deploy taught:** only 1 of 11 production runs reached Langfuse, with no error anywhere.
- FastAPI continues the request's `traceparent`. On Cloud Run that header comes from Google's front end, which marks only a few requests as sampled.
- OpenTelemetry's default sampler follows the parent, so the agent's spans were silently not recorded for the rest. The one trace that arrived had the same id as the one request Cloud Trace sampled.
- Fix: each run starts a trace of its own (always sampled).
- Second fix: export only the Langfuse SDK's spans. The Anthropic SDK emits its own span per call, and it duplicated every model call's cost.
