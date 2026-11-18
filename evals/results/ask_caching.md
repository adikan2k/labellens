# Ask agent: prompt caching, before and after

Measured 2026-11-18 with `uv run python -m scripts.measure_ask_caching --limit 10 --yes`.
Raw per-run and per-call numbers: `evals/results/ask_caching.json`.

- Model `claude-haiku-5-5`, prompt version `ask-v2`, thinking off, all three tools.
- Questions: the first 10 SQL questions of `evals/datasets/ask.jsonl` (sql-01 to sql-10).
- Each question ran twice, one run at a time: "before" with `cache_prompt=False` (system prompt
  as a plain string, no `cache_control`), "after" with one ephemeral `cache_control` marker on the
  system block. The order alternated per question, so neither variant always met the warmer
  database.
- Costs use the corrected `Usage.cost`: cache reads at 0.1x and cache writes at 1.25x the $0.10/MTok
  input price, output at $0.50/MTok.
- Total spent on the measurement: $0.0126.

## Result

The tools and system prompt cache. The cached prefix is **3,344 tokens** (more than the ~2,200
estimated; well over Haiku 5.5's 512-token minimum). The first "after" run wrote it on its first
call and read it on its second; every later "after" run read it on both calls. Every run made two
model calls in both variants, so the comparison is like for like.

| | Before | After | Change |
|---|---|---|---|
| Total cost, 10 runs | $0.009269 | $0.003356 | -64% |
| Mean cost per run | $0.000927 | $0.000336 | -64% |
| Total, every "after" run priced cold (first call writes the prefix) | $0.009269 | $0.006817 | -26% |
| Median latency per run | 2,548 ms | 2,658 ms | no measurable change |
| Mean latency per run | 2,796 ms | 2,629 ms | |
| Median paired difference (after - before) | | | +7 ms |
| Cache write tokens | 0 | 3,344 | |
| Cache read tokens | 0 | 63,536 | |

| Question | Calls (before / after) | Before $ | After $ | Before ms | After ms | Cache write | Cache read |
|---|---|---|---|---|---|---|---|
| sql-01 | 2 / 2 | 0.001128 | 0.000651 | 4,786 | 2,459 | 3,344 | 3,344 |
| sql-02 | 2 / 2 | 0.000898 | 0.000311 | 2,543 | 2,874 | 0 | 6,688 |
| sql-03 | 2 / 2 | 0.000845 | 0.000256 | 2,465 | 2,459 | 0 | 6,688 |
| sql-04 | 2 / 2 | 0.000893 | 0.000298 | 2,360 | 2,386 | 0 | 6,688 |
| sql-05 | 2 / 2 | 0.001025 | 0.000332 | 3,727 | 2,858 | 0 | 6,688 |
| sql-06 | 2 / 2 | 0.000929 | 0.000342 | 3,041 | 2,977 | 0 | 6,688 |
| sql-07 | 2 / 2 | 0.000902 | 0.000318 | 3,200 | 3,120 | 0 | 6,688 |
| sql-08 | 2 / 2 | 0.000793 | 0.000214 | 1,526 | 1,774 | 0 | 6,688 |
| sql-09 | 2 / 2 | 0.000820 | 0.000216 | 1,761 | 1,781 | 0 | 6,688 |
| sql-10 | 2 / 2 | 0.001035 | 0.000417 | 2,553 | 3,600 | 0 | 6,688 |

sql-01 "before" was the first run of the session; its 4.8 s probably includes connection
warm-up, which also flatters the "after" mean. Without it the latency difference is noise in both
directions (-869 ms to +1,047 ms per question). Prefilling 3.3k tokens is fast on Haiku 5.5, so
caching it saves no time we can see at this sample size.

## What this means in production

- **Warm (another question within 5 minutes):** both calls read the prefix. Its input cost per
  two-call run drops from $0.000669 to $0.000067; the whole run costs about a third as much.
- **Cold (first question in 5 minutes):** the first call writes the prefix at 1.25x and the
  second reads it at 0.1x, so the prefix costs $0.000451 instead of $0.000669 (-33%), and the
  whole run about a quarter less. The public demo's traffic is light, so most runs are probably
  cold; caching is still cheaper for them.
- **A one-call run that is cold** (a refusal or an out-of-scope reply, no tool call) pays the
  write premium with nothing to read it back: about $0.00008 more than before. Two or more calls
  in the run, or any traffic within 5 minutes, pays that back.
- The daily spend cap counts `run.cost`, which now prices cache tokens correctly; before this
  change it counted every cached token at the full input price.

## Answers are equivalent

Spot-checked all 10 pairs against the dataset's expected facts. Both variants state every
expected fact for every question (sql-01: 1,323; sql-02: 3,347; sql-03: 25,293; sql-04: 95.5%;
sql-05: 8.85 g; sql-06: 39,492; sql-07: citric acid, 100,764; sql-08: Cheerios, 5.128 g; sql-09:
Coca-Cola Zero Sugar, C, NOVA 4; sql-10: eight additives incl. tartrazine, sunset yellow, allura
red). Wording differs as it does between any two runs. One ordering difference: sql-01 "before"
leads with the 1,178 distinct products and then gives the 1,323 listings, "after" leads with
1,323. No answer gained or lost a fact. Every run used query_sql only; in sql-01 and sql-05 "before"
made two parallel queries where "after" made one, which is ordinary run-to-run variation (both
still took two model calls).

## Decision

Keep it. Every measured run was cheaper, in both the warm and the priced-cold case, the answers
did not change, and latency did not change.
