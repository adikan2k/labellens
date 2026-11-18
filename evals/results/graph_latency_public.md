# Graph and swap latency: public

Measured 2026-11-18T02:32:20+00:00 against `https://labellens-api-1036759996795.us-east4.run.app`: 100 products the
graph holds, one request at a time per endpoint, end to end from the client.

| Endpoint | p50 ms | p95 ms | max ms | first (cold) ms | errors | 1 s target |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `/graph/neighborhood?depth=2` | 292.0 | **406.0** | 757.7 | 1146.6 | 0 | meets |
| `/products/{code}/swaps` | 103.0 | **233.2** | 309.3 | 124.1 | 0 | meets |

The browser adds the layout and first frame on top (measured separately with a
`performance.mark("graph-rendered")`).
