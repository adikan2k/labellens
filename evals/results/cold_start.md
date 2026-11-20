# Cold start

Measured against `https://labellens-api-1036759996795.us-east4.run.app` (revision
`labellens-api-00017-6zm`) from a home connection. Cloud Run runs a minimum of 0 instances, and
Neon suspends its compute after 5 idle minutes, so after a quiet spell the first request starts
both.

## After an hour idle (the launch checklist's case)

Measured 2026-11-18T19:50:12Z. Cloud Run's request log shows the last request before it at
18:43:02Z (the 18:41 smoke test), so the API had been idle for 67 minutes.

| Request | Time |
| --- | ---: |
| First `/search?q=milk` (Cloud Run and Neon both cold) | 22.64 s |
| Second `/search?q=bread` (warm) | 0.11 s |
| Third `/search?q=cheese` (warm) | 0.13 s |

Where the 22 s went, from Cloud Run's own log for that instance:

| Step | From | To | Time |
| --- | --- | --- | ---: |
| Request arrives; an instance starts and imports the app | 19:50:14.6 | 19:50:20.9 | 6.3 s |
| App startup (the FastAPI lifespan) | 19:50:20.9 | 19:50:36.8 | 16.0 s |
| The search itself, Neon waking included | 19:50:36.8 | 19:50:37.1 | 0.2 s |

Neon waking is not the problem: the query, with Neon cold, took about 0.2 s. The lifespan
opens no connections (the pools and the graph driver are lazy). What it does on first run is
import the ask agent's libraries (`anthropic`, `langfuse` with OpenTelemetry, the agent and the
Voyage client). Locally those imports take 3.5 s warm and 47 s from a cold disk cache, so they
are heavy. On a fresh Cloud Run host the image's files are read on demand, which fits a 16 s
lifespan. That is the likely cause, not a proven one: the lifespan logs no timings of its own.
Startup CPU boost is already on.

The web app has no timeout on a search, so a visitor after an hour's quiet watches the loading
state for about 22 s, then everything is fast.

## After 25 minutes idle

Measured 2026-11-18T00:32:03Z, the first time this was checked.

| Request | Time |
| --- | ---: |
| First `/search?q=milk` | 3.90 s |
| Second `/search?q=bread` | 0.10 s |
| Third `/search?q=cheese` | 0.11 s |

Both platforms had scaled down by then too, yet the first request took a sixth of the time.
The likeliest difference is that the instance landed on a host that still had the image's
files cached.

## The fix: the ask agent loads on the first question

Since revision `labellens-api-00018-vng` (PR #19), the ask service is built on the first
`/ask`, not at startup, so a search never waits for its libraries. Startup now logs its own
duration (`Startup took …`), and the first question logs the build (`Ask service ready in …`).

| Startup step (Cloud Run log) | Revision | Time |
| --- | --- | ---: |
| Scale from zero after 67 minutes idle, 19:50 | 00017 | 16.0 s |
| Scale from zero, 18:43 | 00017 | 4.6 s |
| First instance of the new revision, 20:16 | 00018 | 0.41 s |

The startup step no longer imports the ask agent's libraries. A test checks this in a fresh
interpreter, and it fails on the old startup with `['anthropic']`. Not yet measured: a full
hour-idle cold start on revision 00018. The 6.3 s for Cloud Run to start an instance and
import the app is unchanged, so expect roughly 7 s, not 22 s. To confirm, time the same
three searches with `curl -w "%{time_total}"` after an hour with no requests. The first question after a quiet spell
now pays the library load instead of the first search.

A minimum of one instance would remove the cold start entirely but bills every hour; it is
not needed unless the remeasure disappoints.

## After a night idle (2026-11-19, 06:03 UTC)

| Request | Time |
| --- | ---: |
| `GET /health`, first request | 0.13 s |
| `GET /products/{code}`, first database query | 1.06 s |
| Product, search, stats and additive guide after that | 0.09 to 0.15 s |

The Cloud Run instance was already up (the 6-hourly smoke test keeps it busy often enough),
so this run measured Neon waking from its idle pause, about 1 s, not a scale from zero. A
full scale-from-zero on the current revision is still unmeasured; the warm-up script
(`uv run python -m scripts.warm`) removes both before a demo.

## Scale from zero on the current revision (2026-11-19 and 20)

Read from Cloud Run's request log for revision `labellens-api-00022-79f`, not timed by hand:
the first request to arrive at each of five new instances, and the next request after it.

| New instance (UTC) | First request | Time | Next request |
| --- | --- | ---: | ---: |
| 2026-11-19 07:55 | `GET /health` (smoke test) | 7.82 s | 0.06 s |
| 2026-11-19 17:30 | `POST /mcp` (Claude) | 7.45 s | under 0.01 s |
| 2026-11-19 20:58 | `GET /health` (smoke test) | 7.78 s | 0.06 s |
| 2026-11-20 02:12 | `POST /mcp` (Claude) | 7.07 s | under 0.01 s |
| 2026-11-20 06:22 | `POST /mcp` (Claude) | 10.07 s | under 0.01 s |

So a visitor who arrives after a quiet spell waits 7 to 10 s, as predicted above, not 22.6 s.
App startup itself logged 0.3 to 1.9 s on this revision; the rest is Cloud Run starting an
instance and importing the app.

It happens often. The same log shows 28 instance starts on this revision between 2026-11-19
01:14 and 2026-11-20 06:53, about one an hour, because the site is quiet and Cloud Run stops
an idle instance after at most 15 minutes.

To reproduce: `gcloud logging read` on the service for `textPayload:"Startup took"`, then the
request log around each timestamp for `httpRequest.latency`.

## The fix: a ping every 5 minutes, and a line that says what is happening

- `scripts/keep_warm.py` creates one Cloud Scheduler job that asks for `/health` every 5
  minutes, so an instance is almost always up. Minimum instances stays 0, and `/health` opens
  no database connection, so Neon still pauses when idle (about 1 s to wake, measured above).
  It is not a guarantee: Cloud Run can still replace an instance, and the first request after a
  deploy starts a new one.
- When a search on the home page runs longer than 2 seconds, the page now says the search is
  waking up and that the first one can take about 10 seconds. Before, the loading state gave
  no reason.
