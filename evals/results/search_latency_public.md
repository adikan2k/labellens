# Search latency: public

Measured 2026-11-20T08:48:36+00:00 against `https://labellens-api-1036759996795.us-east4.run.app`: 200 sequential requests
to `/search` from `evals/datasets/search_queries.txt`, end to end from the client.

| | ms |
| --- | ---: |
| p50 | 97.8 |
| **p95** | **175.0** |
| p99 | 235.1 |
| max | 268.4 |
| first request (cold, not in the percentiles) | 135.3 |

Errors: 0. Target: p95 under 300 ms. This run **meets** it.

Slowest requests:

| Query | ms |
| --- | ---: |
| `pringles` | 268.4 |
| `salsa` | 240.7 |
| `salsa` | 235.1 |
| `salsa` | 217.3 |
| `kellogg` | 201.7 |

## Run to run (added by hand, 2026-11-20)

The 95th percentile of 200 requests is the tenth slowest, so it moves between runs. Three
runs on this revision, the first with search fetching twice as many rows before folding
duplicate listings:

| Run (UTC) | p50 | p95 | Note |
| --- | ---: | ---: | --- |
| 08:36 | 102.2 | 192.9 | |
| 08:48:02 | 104.6 | 215.7 | began as the database woke: its first request took 3,065 ms |
| 08:48:36 | 97.8 | 175.0 | this report |

The run of 2026-11-18, before that change, gave 103.5 and 184.0. Read the published figure as
"about 175 to 215 ms", not as a difference between revisions.
