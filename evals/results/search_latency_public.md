# Search latency: public

Measured 2026-11-18T08:57:03+00:00 against `https://labellens-api-1036759996795.us-east4.run.app`: 200 sequential requests
to `/search` from `evals/datasets/search_queries.txt`, end to end from the client.

| | ms |
| --- | ---: |
| p50 | 103.5 |
| **p95** | **184.0** |
| p99 | 378.9 |
| max | 15114.6 |
| first request (cold, not in the percentiles) | 124.5 |

Errors: 0. Target: p95 under 300 ms. This run **meets** it.

Slowest requests:

| Query | ms |
| --- | ---: |
| `bre` | 15114.6 |
| `peanut butter` | 522.9 |
| `ice cream` | 378.9 |
| `lays` | 253.3 |
| `orange juice` | 222.5 |
