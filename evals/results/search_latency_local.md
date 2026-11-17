# Search latency: local

Measured 2026-11-17T20:10:19+00:00 against `http://127.0.0.1:8000`: 200 sequential requests
to `/search` from `evals/datasets/search_queries.txt`, end to end from the client.

| | ms |
| --- | ---: |
| p50 | 11.8 |
| **p95** | **38.1** |
| p99 | 128.0 |
| max | 553.5 |
| first request (cold, not in the percentiles) | 66.2 |

Errors: 0. Target: p95 under 300 ms. This run **meets** it.

Slowest requests:

| Query | ms |
| --- | ---: |
| `peanut butter` | 553.5 |
| `ice cream` | 363.9 |
| `great value` | 128.0 |
| `orange juice` | 127.4 |
| `tortilla chips` | 116.6 |
