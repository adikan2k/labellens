# 0006: Food graph and swaps (phase 4)

Status: accepted. Date: 2026-11-18. Phase 4.

## Swaps live in Postgres, not the graph

**Chosen:** `GET /products/{code}/swaps` queries Neon. A partial index on category, grade, additive count and rank, limited to products with no flagged additive, makes the rule one index range scan. On the full data, 400 popular D and E products answer in a p50 of 2.2 ms and a p95 of 5.4 ms.
**Why:**
- Every product page shows swaps, for all 985,260 products.
- The graph holds only 27,662 of them.
- AuraDB Free pauses after 72 idle hours and offers no SLA. A product page should never depend on it.
**Rejected:** computing swaps in Cypher (coverage, and a dependency on the least reliable service).

## Same category is not enough: swaps must be similar

**Chosen:** SPEC's rule (same category, better grade, nothing flagged, ranked by grade then fewest additives), plus similarity by name, in tiers:
1. the head word and another name word
2. the head word only
3. any name word

The head word is the last word of the name before any comma, once generic words like "classic" or "organic" are dropped.
**Why:** the first version offered marinara and soy sauce as swaps for mayonnaise, because "Sauces, dressings and condiments" is broad. With tiers, mayo gets mayos and honey gets honeys. When nothing similar scores better, there are no swaps rather than unrelated filler.

## The flag list is Open Food Facts' own

**Chosen:** additives whose taxonomy entry has `efsa_evaluation_overexposure_risk: high`. That is 38 in the taxonomy and 34 in use on US products, found on 10.8% of them (nitrites, phosphates, carrageenan, MSG, sorbates, benzoates and others).
**Why:** it's data with a source, EFSA's exposure estimates against acceptable daily intakes as recorded by OFF, not our judgement. Swap reasons say "none flagged by Open Food Facts".
**Rejected:**
- Adding "moderate": stricter, with fewer swaps.
- No list: it drops a SPEC rule.

## The graph subset, by rank, to the relationship cap

**Chosen:** graded, named products with a real category, in search rank order (`int_product_rank`, shared with search), added while a running sum of their relationships stays under 360,000.
**Why:**
- Each product's relationships are its own, so the cut-off is exact.
- Nodes never bind: 36,729 against a cap of 180,000.
- `in_graph` in Postgres comes from the same model, so pages link to the explorer only when there is something to show.

On the full data: 27,662 products, 36,729 nodes, 359,995 relationships. 241,427 of the relationships are ingredient links.

## Keeping AuraDB Free alive

**Chosen:** a GitHub Actions workflow runs one read every 48 hours, and the weekly pipeline reloads the graph.
**Why:** AuraDB Free pauses after 72 hours without activity, and deletes an instance paused for more than 30 days.

## Explorer: Sigma 4, laid out before the first frame

**Chosen:**
- Sigma.js 4 on graphology.
- ForceAtlas2 run for a fixed number of iterations before the first frame, so nothing moves on its own.
- Colours read from the CSS tokens at runtime.
- A label-style panel for the selected node.
- The same nodes as a list, for keyboard and screen readers, since the WebGL canvas is hidden from assistive technology.

Depth-2 neighbourhoods add the best-ranked six products per hub, capped at 150 nodes.

## Testing against real Neo4j

**Chosen:** a Neo4j 2025 server in docker-compose and CI. A separate `neo4j-test` server lets tests replace their graph without touching the development one.
**Why:** a fake session can't catch Cypher syntax, and the batched `CALL () { … } IN TRANSACTIONS` delete and the scoped subqueries need a recent Neo4j.

## Measured

- **Swaps** (full data, local): p50 2.2 ms, p95 5.4 ms. 12 of 400 popular D and E products get none.
- **Neighbourhood, depth 2** (local): p50 27.5 ms, p95 42.8 ms. Median 44 nodes, largest 120.
- **Public, from a home connection** (`evals/results/graph_latency_public.md`, 100 products):
  - neighbourhood p50 292 ms, p95 406 ms
  - swaps p50 103 ms, p95 233 ms
  - the first version made two round trips to Aura (p50 498, p95 708); one query saved about 200 ms
- **In the browser, on the deployed preview:**
  - A first visit drew the graph 2.5 s after navigation. With the server fetching the data (cached) and Sigma loading early, a visit to a recently viewed product now draws in 628 ms with no browser API call.
  - Re-centring took 0.7–1.1 s through a page render. In the browser it's now 0.18–0.95 s, typically about 0.2 s.

## AuraDB and Windows certificates

**Chosen:** the Neo4j driver trusts the Mozilla CA bundle (`certifi`) for encrypted connections.
**Why:** AuraDB's certificate chains to an SSL.com root that this Windows machine's certificate store hadn't installed. Python failed with "self-signed certificate in certificate chain", while Windows' own TLS and certifi both verified it. One trust source works the same on Windows, Linux and CI.
