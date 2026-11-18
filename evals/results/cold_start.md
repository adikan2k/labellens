# Cold start

Measured 2026-11-18T00:32:03Z against `https://labellens-api-1036759996795.us-east4.run.app`
from a home connection, after 25 minutes with no requests. By then Cloud Run had scaled the
API to zero instances (minimum 0) and Neon had suspended its compute (after 5 idle minutes),
so the first request starts both.

| Request | Time |
| --- | ---: |
| First `/search?q=milk` (Cloud Run and Neon both cold) | 3.90 s |
| Second `/search?q=bread` (warm) | 0.10 s |
| Third `/search?q=cheese` (warm) | 0.11 s |

The web shows "Search is waking up" if the API takes longer than its timeout, so a visitor
after a quiet spell sees one slow search, then normal speed. Keeping a minimum instance warm
would remove most of this but costs money every hour; the launch checklist asks for the
cold start to be timed and noted, not removed.

The launch checklist asks for an hour idle; this was 25 minutes, past both platforms'
scale-down points. Remeasure at an hour before launch.
