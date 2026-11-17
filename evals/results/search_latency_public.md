# Search latency: public

Measured 2026-11-17T22:32:12+00:00 against `https://labellens-api-1036759996795.us-east4.run.app`: 200 sequential requests
to `/search` from `evals/datasets/search_queries.txt`, end to end from the client.

| | ms |
| --- | ---: |
| p50 | 102.2 |
| **p95** | **193.0** |
| p99 | 302.1 |
| max | 395.1 |
| first request (cold, not in the percentiles) | 108.8 |

Errors: 0. Target: p95 under 300 ms. This run **meets** it.

Slowest requests:

| Query | ms |
| --- | ---: |
| `ice cream` | 395.1 |
| `5449000054227` | 316.8 |
| `great value` | 302.1 |
| `yog` | 299.1 |
| `water` | 296.4 |
