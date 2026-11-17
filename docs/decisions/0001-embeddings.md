# 0001: Embeddings provider

Status: accepted (draft for Aditya to rewrite) · Date: 2026-11-17 · Phase 0

## What we need

Vector search for one tool: `search_explainers` in the ask agent (phase 5). It searches the additive and ingredient explainers, which number a few thousand short texts, written once each in phase 3. The vectors live in Neon with pgvector, inside the 1 GB free plan.

So the corpus is small and written once, queries are short, and cost and latency matter more than the last point of retrieval quality.

## Chosen: Voyage AI, `voyage-4-lite`

- **Price.** $0.02 per million tokens, with 200 million free tokens per account. The Batch API is a further 33% cheaper, but free tokens don't apply to it. (docs.voyageai.com/docs/pricing, checked 2026-11-17)
- **Fit.** 32,000-token context and 1024 dimensions by default (256, 512 and 2048 also available). `input_type` takes `query` or `document`, which suits short questions searched against longer explainers. (docs.voyageai.com/docs/embeddings)
- **Cost here.** About 8,000 explainers at about 100 tokens each is about 0.8 million tokens, roughly $0.02 at list price and inside the free allowance. Query traffic is negligible.
- **Storage.** 8,000 × 1024 float32 is about 33 MB in pgvector, well under the 800 MB load limit.
- **Ecosystem.** Anthropic's documentation points to Voyage for embeddings, so the project stays on one recommended path.

Model name lives in config (`EMBEDDINGS_MODEL`), so moving to `voyage-4` or `voyage-4-large` is a config change plus a re-embed. All 4-series models produce compatible embeddings.

## Rejected

- **OpenAI `text-embedding-3-small`.** Cheap and widely used, but it adds a second model vendor, a second bill and a second set of keys to a Claude-based project, for no gain at this corpus size.
- **Google Gemini embeddings.** We already need a Google Cloud project for Cloud Run, but service-account or ADC auth is heavier than one API key, and it would tie embeddings to the deploy platform.
- **Local model (e.g. `voyage-4-nano` open weights, or sentence-transformers).** No API cost, but it adds a large dependency and model download to the API image on Cloud Run, which hurts cold starts.

## Consequences

- One more account and key: `EMBEDDINGS_API_KEY` (spec section 4).
- Phase 5 picks the dimension (1024 unless storage says otherwise) and records it with the pgvector column.
- Free tokens are a trial allowance; the price above is what we budget against.
