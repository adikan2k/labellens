# Graph and swap latency: local

Measured 2026-11-18T02:03:27+00:00 against `http://127.0.0.1:8000`: 60 products the
graph holds, one request at a time per endpoint, end to end from the client.

| Endpoint | p50 ms | p95 ms | max ms | first (cold) ms | errors | 1 s target |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `/graph/neighborhood?depth=2` | 27.5 | **42.8** | 59.2 | 414.4 | 0 | meets |
| `/products/{code}/swaps` | 5.4 | **24.9** | 28.5 | 5.1 | 0 | meets |

The browser adds the layout and first frame on top (measured separately with a
`performance.mark("graph-rendered")`).
