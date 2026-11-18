"""Scoring for the category eval, on fixed data."""

from __future__ import annotations

from pathlib import Path

import pytest

from evals.runners import category_accuracy as acc


def test_accuracy_counts_invalid_answers_as_wrong() -> None:
    s = acc.score([("cheese", "cheese"), ("milk", "milk"), ("milk", "yogurt"), ("sodas", None)])
    assert (s.n, s.correct, s.accuracy, s.invalid) == (4, 2, 0.5, 1)


def test_recall_precision_and_confusions() -> None:
    pairs = [
        ("milk", "milk"),
        ("milk", "yogurt"),
        ("milk", "yogurt"),
        ("yogurt", "yogurt"),
        ("sodas", None),
    ]
    s = acc.score(pairs)
    assert s.per_category["milk"] == {
        "support": 3,
        "predicted": 1,
        "recall": 0.333,
        "precision": 1.0,
    }
    assert s.per_category["yogurt"]["precision"] == pytest.approx(0.333)
    assert s.confusions[0] == ("milk", "yogurt", 2)
    assert ("sodas", "(invalid)", 1) in s.confusions


def test_the_split_is_fixed_and_roughly_even() -> None:
    codes = [f"{n:013d}" for n in range(1000)]
    halves = [acc.half(c) for c in codes]
    assert halves == [acc.half(c) for c in codes]
    assert 400 < halves.count("dev") < 600


def test_markdown_reports_the_verdict_and_tables() -> None:
    pairs = [("milk", "milk")] * 9 + [("milk", "cheese")]
    report = acc.Report(
        label="m-full",
        model="m",
        prompt_version="categories-v1",
        inputs="name, brand and ingredients",
        measured_at="2026-11-18T00:00:00+00:00",
        overall=acc.score(pairs),
        tag_baseline=acc.score(pairs[:5]),
    )
    text = acc.to_markdown(report, {"milk": "Milk, cream and plant milks", "cheese": "Cheese"})
    assert "| **All labelled products** | **9/10: 90.0% (59.6–98.2%)** |" in text
    assert report.overall.ci95 == [0.5958, 0.9821]
    assert "95% confidence intervals (Wilson score)" in text
    assert "This run **meets** it." in text
    assert "| Milk, cream and plant milks | Cheese | 1 |" in text
    assert "Baseline: Open Food Facts' tags" in text


def test_missing_gold_file_explains_how_to_make_it(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=r"scripts/label.py"):
        acc.load_gold(tmp_path / "nope.csv")
