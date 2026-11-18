"""Lighthouse eval: scores for the main pages of a deployed web app.

    uv run python -m evals.runners.lighthouse --base-url https://labellens-beige.vercel.app

Runs Lighthouse (mobile, its default) through npx on home, a product and the dashboard, and
writes evals/results/lighthouse.md: the four category scores plus LCP, CLS and TBT per page,
against the SPEC target of 90. Needs Node and Chrome; the raw reports go to a temporary folder
and are not kept. No paid calls.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
LIGHTHOUSE = "lighthouse@13.6.0"
TARGET = 90
PAGES = {
    "Home": "/",
    "Product": "/product/0016000275287",
    "Dashboard": "/dashboard",
}
CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]


@dataclass
class PageScore:
    page: str
    url: str
    scores: dict[str, int]
    lcp: str
    cls: str
    tbt: str

    @property
    def meets_target(self) -> bool:
        return all(score >= TARGET for score in self.scores.values())


def parse_report(page: str, report: dict) -> PageScore:
    categories = report["categories"]
    audits = report["audits"]
    return PageScore(
        page=page,
        url=report["finalDisplayedUrl"],
        scores={key: round(categories[key]["score"] * 100) for key in CATEGORIES},
        lcp=audits["largest-contentful-paint"]["displayValue"],
        cls=audits["cumulative-layout-shift"]["displayValue"],
        tbt=audits["total-blocking-time"]["displayValue"],
    )


def run_lighthouse(url: str, out: Path) -> dict:
    npx = shutil.which("npx")
    if not npx:
        raise SystemExit("npx not found. Install Node.js 22 or later.")
    subprocess.run(
        [
            npx,
            "-y",
            LIGHTHOUSE,
            url,
            "--quiet",
            "--chrome-flags=--headless=new",
            f"--only-categories={','.join(CATEGORIES)}",
            "--output=json",
            f"--output-path={out}",
        ],
        check=True,
    )
    return json.loads(out.read_text("utf-8"))


def to_markdown(base_url: str, results: list[PageScore]) -> str:
    rows = "\n".join(
        f"| {r.page} | {' | '.join(str(r.scores[c]) for c in CATEGORIES)} | {r.lcp} | {r.cls} "
        f"| {r.tbt} |"
        for r in results
    )
    verdict = "meet" if all(r.meets_target for r in results) else "do not all meet"
    measured = datetime.now(UTC).isoformat(timespec="seconds")
    return f"""# Lighthouse

Measured {measured} against `{base_url}` with {LIGHTHOUSE} (mobile, default throttling).

| Page | Performance | Accessibility | Best practices | SEO | LCP | CLS | TBT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}

Target: every category at least {TARGET}. These pages **{verdict}** it.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lighthouse scores for the deployed web app.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, default=RESULTS / "lighthouse.md")
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for page, path in PAGES.items():
            report = run_lighthouse(base + path, Path(tmp) / f"{page}.json")
            results.append(parse_report(page, report))

    text = to_markdown(base, results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, "utf-8", newline="\n")
    print(text)
    return 0 if all(r.meets_target for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
