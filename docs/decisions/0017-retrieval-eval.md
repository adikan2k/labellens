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

- **E-numbers were almost never found: 1 of 30, by every method.** The text that was embedded is "Name: explainer", and only 14 of 1,019 contain an E-number. Neither kind of search can match a code that is not there, so a question like "What is E412?" depended on the agent choosing SQL instead. Fixed the same day (below).
- **Otherwise the vector search is strong.** Names 100%, misspellings 97%, descriptions without the name 92%. Keyword search drops to 57% on misspellings, as expected.
- **Hybrid does not help here.** It sits between the two (68% against 74%), because keyword search is weaker on everything except exact names.
- **No clean cut-off for off-topic questions.** The best off-topic match scores up to 0.289; some answerable queries score as low as 0.211.
- **Some explainers have poor names.** 11 additives are named only by their code ("E411 food additive"), and one has a Catalan name.

## Fixed: E-numbers are looked up exactly (2026-11-25)

**Chosen:** before the vector search, the tool reads any E-number out of the question ("E412", "e330", "E339(iii)") and returns that additive's explainer first, or the closest narrower one when only that is written (E322 asked, E322i written). The vector results fill the rest of the five. The eval imports the same two functions, so it measures what the tool does.

**Result:** the agent's search finds the right explainer in its top 5 for 98% (93–99%) of the 125 questions, up from 74%; all 30 E-number questions, up from 1. Names, misspellings and descriptions are unchanged.

**Rejected:**
- **Putting the E-number into the embedded text and re-embedding:** it would help keyword search more than vector search, which matches codes poorly, and it needs a reload of the live database. An exact lookup is certain and costs nothing.
- **Reading "E 400" with a space as an E-number:** "vitamin E 400 IU" would become alginic acid.

**What the 98% does not show:** the E-number questions were built from additives that have an explainer, so the lookup cannot miss them. From now on the eval guards that behaviour rather than measuring something hard. The 3 misses left are one misspelling and two descriptions.

## Next

- Measure faithfulness: whether explainer answers say only what the retrieved text says.
- The same exact lookup for common names the MCP server already knows ("MSG", "baking soda").
