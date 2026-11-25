# 0017: A retrieval eval for the explainer search

Status: accepted. Date: 2026-11-25.

The ask agent's one retrieval step, `search_explainers`, was only tested end to end: 10 questions in the ask eval, each naming the additive outright. The agent and the explainer-only baseline both scored 1.00 on them, so they could not tell good retrieval from bad. An AI engineer would ask how retrieval was measured, and there was no answer.

## Chosen: measure the search itself, against baselines, mostly with answers from the data

- **The agent's own search, offline.** The tool runs exact cosine search in pgvector over vectors that are committed (`explainer_embeddings.parquet`, the file the loader reads). The eval runs the same exact search on the same vectors in DuckDB, so it needs no database and gives the same order.
- **Two baselines on the same text.** Keyword search (BM25 over "Name: explainer", the text that was embedded) and a hybrid of the two (reciprocal rank fusion). A vector score alone says nothing without something to beat.
- **Answers from the data where possible.** 100 of the 145 queries are names, E-numbers and misspelt names, with answers taken from Open Food Facts. Class queries ("something that keeps oil and water mixed") take their answers from Open Food Facts' additive classes. Only 25 descriptive queries ("baking soda", "the red dye in candy") and 10 off-topic ones were written with their answers by Claude Code, and the report says so.
- **Fair answers.** A parent or child additive counts (E322 Lecithins for E322i Lecithin), because Open Food Facts writes an explainer for each. A sibling does not (E160a beta-carotene is not E160b annatto).
- **Metrics the agent's use explains.** Hit@5, because the tool returns 5; hit@1 and MRR@10 as well. Wilson intervals, as in every other report.
- **Spread across how common things are.** Name, E-number and misspelling queries are picked evenly from the most to the least listed additives and ingredients.
- **Nearly free.** Only the 145 queries go to Voyage (about 1,000 tokens), once; their vectors are committed, so a rerun costs nothing.

**Rejected:**
- **Writing every query and answer with a model:** quicker, but the eval would partly grade a model with a model. Most answers here come from the data instead.
- **Faithfulness first** (does the answer stick to the retrieved text?): worth doing, but it needs a judge model and says nothing if the right text was never retrieved. Retrieval comes first.
- **Postgres full-text search as the keyword baseline:** closer to the stack, but it needs a running database. BM25 is the standard baseline and runs anywhere.

## What it found

- **E-numbers are almost never found: 1 of 30, by every method.** The text that was embedded is "Name: explainer", and only 14 of 1,019 contain an E-number. Neither kind of search can match a code that is not there. A question like "What is E412?" depends on the agent choosing SQL instead.
- **Otherwise the vector search is strong.** Names 100%, misspellings 97%, descriptions without the name 92%. Keyword search drops to 57% on misspellings, as expected.
- **Hybrid does not help here.** It sits between the two (68% against 74%), because keyword search is weaker on everything except exact names.
- **No clean cut-off for off-topic questions.** The best off-topic match scores up to 0.289; some answerable queries score as low as 0.211.
- **Some explainers have poor names.** 11 additives are named only by their code ("E411 food additive"), and one has a Catalan name.

## Next

- Look up E-numbers exactly before searching (a few lines in the tool), or put the E-number into the embedded text and re-embed (under a cent, then a reload).
- Then measure faithfulness: whether explainer answers say only what the retrieved text says.
