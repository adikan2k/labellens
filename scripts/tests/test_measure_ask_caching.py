"""The caching measurement: a cold run's price and the comparison table, without the API."""

from __future__ import annotations

from typing import Any

import pytest

from scripts import measure_ask_caching as measure

MODEL = "claude-haiku-5-5"


def _row(variant: str, cost: float, calls: list[dict[str, int]]) -> dict[str, Any]:
    return {
        "id": "sql-01",
        "variant": variant,
        "ms": 2000,
        "cost_usd": cost,
        "model_calls": len(calls),
        "cache_creation_input_tokens": sum(c["cache_write"] for c in calls),
        "cache_read_input_tokens": sum(c["cache_read"] for c in calls),
        "calls": calls,
    }


def test_a_warm_run_is_priced_cold_by_writing_its_first_read() -> None:
    warm = _row("after", 0.001, [{"cache_write": 0, "cache_read": 2000}])
    # 2,000 tokens at 1.25x instead of 0.1x of $0.10/MTok
    assert measure.cold_cost(warm, MODEL) == pytest.approx(0.001 + 2000 * 1.15 * 0.10 / 1e6)
    cold = _row("after", 0.001, [{"cache_write": 2000, "cache_read": 0}])
    assert measure.cold_cost(cold, MODEL) == pytest.approx(0.001)


def test_the_table_has_a_row_per_question_and_a_summary_per_variant() -> None:
    rows = [
        _row("before", 0.002, [{"cache_write": 0, "cache_read": 0}] * 2),
        _row("after", 0.001, [{"cache_write": 2000, "cache_read": 0},
                              {"cache_write": 0, "cache_read": 2000}]),
    ]  # fmt: skip
    out = measure.table(rows, MODEL)
    assert "| sql-01 | 2 / 2 | 0.002000 | 0.001000 | 2,000 | 2,000 | 2,000 | 2,000 |" in out
    assert "- before: total $0.002000" in out and "- after: total $0.001000" in out
