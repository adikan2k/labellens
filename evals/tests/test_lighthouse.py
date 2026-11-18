"""The Lighthouse runner's report parsing and summary, on a minimal report shape."""

from __future__ import annotations

from evals.runners import lighthouse


def _report(scores: dict[str, float], cls: str = "0") -> dict:
    return {
        "finalDisplayedUrl": "https://example.vercel.app/",
        "categories": {key: {"score": value} for key, value in scores.items()},
        "audits": {
            "largest-contentful-paint": {"displayValue": "0.8 s"},
            "cumulative-layout-shift": {"displayValue": cls},
            "total-blocking-time": {"displayValue": "10 ms"},
        },
    }


ALL_GOOD = {"performance": 1.0, "accessibility": 1.0, "best-practices": 0.96, "seo": 1.0}


def test_scores_are_percentages_and_metrics_kept() -> None:
    page = lighthouse.parse_report("Home", _report(ALL_GOOD))
    assert page.scores == {
        "performance": 100,
        "accessibility": 100,
        "best-practices": 96,
        "seo": 100,
    }
    assert (page.lcp, page.cls, page.tbt) == ("0.8 s", "0", "10 ms")
    assert page.meets_target


def test_one_category_under_90_misses_the_target() -> None:
    page = lighthouse.parse_report("Product", _report({**ALL_GOOD, "performance": 0.89}))
    assert not page.meets_target


def test_summary_has_a_row_per_page_and_a_verdict() -> None:
    good = lighthouse.parse_report("Home", _report(ALL_GOOD))
    slow = lighthouse.parse_report("Product", _report({**ALL_GOOD, "performance": 0.5}, "0.3"))
    text = lighthouse.to_markdown("https://example.vercel.app", [good, slow])
    assert "| Home | 100 | 100 | 96 | 100 | 0.8 s | 0 | 10 ms |" in text
    assert "| Product | 50 |" in text
    assert "**do not all meet**" in text
