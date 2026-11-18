"""Warm everything up before a demo, and say what could still go wrong during it.

    uv run python -m scripts.warm              # wake every layer, then report
    uv run python -m scripts.warm --hold 45    # and keep it warm for 45 minutes

Run it about ten minutes before. Read-only, and it makes no model call, so it costs nothing.

1. Wakes each layer by running the production smoke test with a patient timeout: Cloud Run
   (an hour-idle cold start took 22.6 s), Neon (suspends after 5 idle minutes), the graph on
   AuraDB Free (pauses after days idle), MCP, and every page.
2. GET /ready builds the ask agent and the label reader, whose libraries are slow to import
   on a fresh instance, so the first question or label in the demo doesn't pay for it. It
   also says what is left: today's spend against the cap, and this address's questions and
   label reads this hour. Run it from the network you will demo on: the hourly limits are
   per address.
3. With --hold, pings /health and /search every 4 minutes so nothing goes back to sleep.

Exits 0 only when everything is ready.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from typing import Any, TextIO

import httpx

from scripts import smoke

TIMEOUT = 90.0  # a cold start, with room
HOLD_EVERY_SECONDS = 240  # under Neon's 5 idle minutes
LOW = 3  # warn when fewer questions or label reads than this are left
GRAPH_HELP = (
    "The graph did not answer. AuraDB Free pauses an idle instance: open "
    "https://console.neo4j.io, resume it (about a minute), then run this again. "
    "`uv run python -m pipeline.load.graph --ping` checks it directly."
)


def ready(api: str, timeout: float = TIMEOUT) -> dict[str, Any]:
    headers = {"User-Agent": "labellens-warm/1"}
    response = httpx.get(f"{api.rstrip('/')}/ready", timeout=timeout, headers=headers)
    response.raise_for_status()
    return response.json()


def problems(results: list[smoke.Result], state: dict[str, Any] | None) -> list[str]:
    """What would bite during a demo, most serious first. Empty means ready."""
    found = []
    for result in results:
        if not result.ok:
            found.append(f"{result.name} failed: {result.detail}")
    if any(not r.ok and "graph" in r.name for r in results):
        found.append(GRAPH_HELP)
    if state is None:
        found.append("GET /ready did not answer, so the ask agent and label reader are cold.")
        return found
    if not state["ask_configured"]:
        found.append("The ask agent is not configured on the API.")
    if not state["label_configured"]:
        found.append("The label reader is not configured on the API.")
    left = state["daily_cap_usd"] - state["spent_today_usd"]
    if left <= 0:
        found.append(
            "Today's spend cap is used up: questions get recorded examples and label reads "
            "are refused until midnight UTC. Use the sample labels."
        )
    if state["questions_left"] == 0:
        found.append("No questions left this hour from this address.")
    if state["label_reads_left"] == 0:
        found.append("No label reads left this hour from this address.")
    return found


def report(state: dict[str, Any], out: TextIO) -> None:
    left = max(0.0, state["daily_cap_usd"] - state["spent_today_usd"])
    print(
        f"Spent today: ${state['spent_today_usd']:.4f} of ${state['daily_cap_usd']:.2f} "
        f"(${left:.4f} left, about {int(left / 0.002)} label reads or {int(left / 0.004)} "
        "questions).",
        file=out,
    )
    for what, key in (("Questions", "questions_left"), ("Label reads", "label_reads_left")):
        note = "  <- low" if 0 < state[key] < LOW else ""
        print(f"{what} left this hour from this address: {state[key]}{note}", file=out)


def hold(
    api: str,
    minutes: float,
    *,
    out: TextIO,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    every: float = HOLD_EVERY_SECONDS,
) -> int:
    """Ping until `minutes` have passed. Returns how many pings failed."""
    api = api.rstrip("/")
    deadline = clock() + minutes * 60
    failures = 0
    print(f"Keeping it warm for {minutes:g} minutes (Ctrl+C to stop).", file=out, flush=True)
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": "labellens-warm/1"}) as client:
        while clock() < deadline:
            sleep(min(every, max(0.0, deadline - clock())))
            started = time.perf_counter()
            try:
                client.get(f"{api}/health").raise_for_status()
                client.get(f"{api}/search", params={"q": "milk", "limit": 1}).raise_for_status()
                line = f"warm  {time.perf_counter() - started:5.2f}s"
            except httpx.HTTPError as error:
                failures += 1
                line = f"FAIL  {type(error).__name__}: {error}"
            print(f"{time.strftime('%H:%M:%S')}  {line}", file=out, flush=True)
    return failures


def run(api: str, web: str, *, out: TextIO | None = None, timeout: float = TIMEOUT) -> list[str]:
    """Wake everything and report. Returns the problems found (empty when ready)."""
    stream: TextIO = out or sys.stdout
    results = smoke.run(api, web, expect_unknown_404=True, out=stream, timeout=timeout)
    state: dict[str, Any] | None
    try:
        state = ready(api, timeout)
    except (httpx.HTTPError, ValueError):
        state = None
    if state is not None:
        report(state, stream)
    found = problems(results, state)
    if found:
        print("\nNot ready:", file=stream)
        for problem in found:
            print(f"- {problem}", file=stream)
    else:
        slowest = max(results, key=lambda r: r.seconds)
        print(
            f"\nReady. The slowest check was {slowest.name} at {slowest.seconds:.1f} s; "
            "everything is warm now.",
            file=stream,
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Warm LabelLens up before a demo.")
    parser.add_argument("--api", default=smoke.API)
    parser.add_argument("--web", default=smoke.WEB)
    parser.add_argument("--hold", type=float, default=0, metavar="MINUTES", help="then keep warm")
    args = parser.parse_args(argv)

    found = run(args.api, args.web)
    if args.hold > 0:
        try:
            hold(args.api, args.hold, out=sys.stdout)
        except KeyboardInterrupt:
            print("Stopped.")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
