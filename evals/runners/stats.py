"""Uncertainty for the eval reports: small samples need intervals, not just percentages.

- `wilson`: the Wilson score interval for a proportion (k successes in n). It stays inside
  [0, 1] and behaves at 0/n and n/n, where the textbook p ± z·√(p(1−p)/n) collapses to a
  zero-width interval.
- `bootstrap_mean`: a percentile bootstrap interval for a mean of per-item values (such as the
  ask eval's fact score), with a fixed seed so a rerun gives the same report.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence

Z95 = 1.96
INTERVAL_NOTE = (
    "Ranges in brackets are 95% confidence intervals (Wilson score): with this few cases the "
    "true rate could plausibly be anywhere in the range, so a gap smaller than the ranges "
    "may be noise."
)


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """The Wilson score interval for successes/n. With n = 0 nothing is known: (0, 1)."""
    if n < 0 or not 0 <= successes <= max(n, 0):
        raise ValueError(f"need 0 <= successes <= n, got {successes}/{n}")
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z / denom * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))
    return max(0.0, centre - half), min(1.0, centre + half)


def ci95(successes: int, n: int) -> list[float]:
    """The Wilson interval rounded for JSON, as [low, high]."""
    low, high = wilson(successes, n)
    return [round(low, 4), round(high, 4)]


def pct_ci(successes: int, n: int, digits: int = 0) -> str:
    """'97% (83–99%)': the share with its 95% Wilson interval; 'none' when n is 0."""
    if n == 0:
        return "none"
    low, high = wilson(successes, n)
    f = f".{digits}f"
    return f"{100 * successes / n:{f}}% ({100 * low:{f}}–{100 * high:{f}}%)"


def bootstrap_mean(
    values: Sequence[float], reps: int = 10_000, seed: int = 0, level: float = 0.95
) -> tuple[float, float]:
    """A percentile bootstrap interval for the mean of values (fixed seed: reproducible)."""
    if not values:
        return 0.0, 1.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(reps))
    tail = (1 - level) / 2
    return means[int(tail * (reps - 1))], means[math.ceil((1 - tail) * (reps - 1))]
