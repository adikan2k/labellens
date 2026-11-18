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
