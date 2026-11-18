"""Confidence intervals for the eval reports, against published values."""

from __future__ import annotations

import pytest

from evals.runners.stats import bootstrap_mean, ci95, pct_ci, wilson


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        # Wilson score intervals at z = 1.96 (Newcombe 1998, and any statistics package).
        (5, 10, 0.2366, 0.7634),
        (0, 10, 0.0, 0.2775),
        (10, 10, 0.7225, 1.0),
        (29, 30, 0.8333, 0.9941),
        (180, 200, 0.8506, 0.9343),
    ],
)
def test_wilson_matches_known_values(k: int, n: int, low: float, high: float) -> None:
    assert wilson(k, n) == pytest.approx((low, high), abs=1e-4)


def test_wilson_with_no_cases_knows_nothing() -> None:
    assert wilson(0, 0) == (0.0, 1.0)
    assert pct_ci(0, 0) == "none"


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson(3, 2)
    with pytest.raises(ValueError):
        wilson(-1, 5)


def test_a_wider_z_gives_a_wider_interval() -> None:
    narrow, wide = wilson(8, 10, z=1.0), wilson(8, 10, z=2.576)
    assert wide[0] < narrow[0] < 0.8 < narrow[1] < wide[1]


def test_formatting_for_reports_and_json() -> None:
    assert pct_ci(29, 30) == "97% (83–99%)"
    assert pct_ci(180, 200, digits=1) == "90.0% (85.1–93.4%)"
    assert ci95(29, 30) == [0.8333, 0.9941]


def test_bootstrap_is_reproducible_and_brackets_the_mean() -> None:
    values = [1.0] * 40 + [0.5, 0.0, 0.75]
    low, high = bootstrap_mean(values)
    assert bootstrap_mean(values) == (low, high)
    assert low < sum(values) / len(values) <= high <= 1.0
    assert bootstrap_mean([1.0, 1.0]) == (1.0, 1.0)
    assert bootstrap_mean([]) == (0.0, 1.0)
