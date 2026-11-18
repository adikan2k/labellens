"""The demo warm-up against the smoke test's stub: ready, not ready, and holding warm."""

from __future__ import annotations

import io
from typing import Any

from scripts import smoke, warm
from scripts.tests.test_smoke import GET, Stub, stub  # noqa: F401  (stub is a fixture)

READY = GET["/ready"]


def _run(base: str) -> tuple[list[str], str]:
    out = io.StringIO()
    found = warm.run(base, f"{base}/web/", out=out, timeout=5)
    return found, out.getvalue()


def test_everything_awake_is_ready_and_says_what_is_left(stub: tuple[Stub, str]) -> None:  # noqa: F811
    _, base = stub
    found, printed = _run(base)
    assert found == [], printed
    assert "Spent today: $0.0200 of $0.50" in printed
    assert "Questions left this hour from this address: 10" in printed
    assert "Label reads left this hour from this address: 10" in printed
    assert "Ready. The slowest check was" in printed


def test_a_paused_graph_says_how_to_resume_it(stub: tuple[Stub, str]) -> None:  # noqa: F811
    state, base = stub
    state.overrides["/graph/neighborhood"] = (503, {"detail": "waking up"})
    found, printed = _run(base)
    assert any("graph" in p and "failed" in p for p in found)
    assert warm.GRAPH_HELP in found and "console.neo4j.io" in printed
    assert "Not ready:" in printed


def test_a_spent_cap_and_used_up_limits_are_problems(stub: tuple[Stub, str]) -> None:  # noqa: F811
    state, base = stub
    spent = READY | {"spent_today_usd": 0.5, "questions_left": 0, "label_reads_left": 2}
    state.overrides["/ready"] = (200, spent)
    found, printed = _run(base)
    assert any("spend cap is used up" in p for p in found)
    assert "No questions left this hour from this address." in found
    assert "Label reads left this hour from this address: 2  <- low" in printed


def test_problems_without_ready_or_configuration() -> None:
    ok = [smoke.Result("api /health", True, "", 0.1)]
    assert "did not answer" in warm.problems(ok, None)[0]
    state: dict[str, Any] = READY | {"ask_configured": False, "label_configured": False}
    assert warm.problems(ok, state) == [
        "The ask agent is not configured on the API.",
        "The label reader is not configured on the API.",
    ]


def test_hold_pings_until_the_time_is_up(stub: tuple[Stub, str]) -> None:  # noqa: F811
    state, base = stub
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    out = io.StringIO()
    failures = warm.hold(base, 10, out=out, sleep=sleep, clock=lambda: now[0])
    assert failures == 0
    assert slept == [240, 240, 120]  # 10 minutes: two full waits, then the rest
    pinged = [path for method, path, *_ in state.requests if method == "GET"]
    assert pinged.count("/health") == 3
    assert sum(p.startswith("/search") for p in pinged) == 3
    assert out.getvalue().count("warm") >= 3


def test_hold_counts_failed_pings(stub: tuple[Stub, str]) -> None:  # noqa: F811
    state, base = stub
    state.overrides["/health"] = (503, {"detail": "down"})
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    out = io.StringIO()
    assert warm.hold(base, 4, out=out, sleep=sleep, clock=lambda: now[0]) == 1
    assert "FAIL" in out.getvalue()
