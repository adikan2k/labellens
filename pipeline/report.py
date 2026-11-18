"""Write the pipeline run report: pipeline/reports/<snapshot-date>.md.

    uv run python -m pipeline.report [--db data/labellens.duckdb]
                                      [--run-results pipeline/dbt/target/run_results.json]

Reads the built DuckDB file, the snapshot's manifests and dbt's run_results.json from the last
`dbt build`. Reports row counts and per-column null rates for every mart, dbt test totals,
and every count the cleaning changed or dropped, so nothing disappears silently.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "labellens.duckdb"
RUN_RESULTS = ROOT / "pipeline" / "dbt" / "target" / "run_results.json"
REPORTS_DIR = ROOT / "pipeline" / "reports"

MARTS = [
    "dim_products",
    "fct_nutrition",
    "dim_additives",
    "bridge_product_additives",
    "dim_ingredients",
    "bridge_product_ingredients",
    "dim_categories",
]
NUTRIENTS = [
    "energy_kcal_100g",
    "sugars_100g",
    "salt_100g",
    "fat_100g",
    "saturated_fat_100g",
    "fiber_100g",
    "proteins_100g",
]


def _n(value: object) -> str:
    return f"{int(value):,}" if isinstance(value, int | float) else str(value)


def _pct(part: int, whole: int) -> str:
    if not whole:
        return "n/a"
    share = 100 * part / whole
    return "<0.1%" if 0 < share < 0.05 else f"{share:.1f}%"


def _products(n: int) -> str:
    return f"{_n(n)} product{'' if n == 1 else 's'}"


class Report:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self.con = con

    def one(self, sql: str) -> Any:
        row = self.con.execute(sql).fetchone()
        assert row is not None
        return row[0]

    def rows(self, sql: str) -> list[tuple[Any, ...]]:
        return self.con.execute(sql).fetchall()


def _snapshot_section(r: Report) -> tuple[str, list[str]]:
    snapshot_dir = ROOT / r.one("select any_value(snapshot_dir) from base_off__us_products")
    manifest = _read_json(snapshot_dir / "manifest.json")
    taxonomy = _read_json(snapshot_dir / "additives.manifest.json")
    date = manifest.get("snapshot_date", snapshot_dir.name)
    lines = [
        "## Snapshot",
        "",
        "| | |",
        "| --- | --- |",
        f"| Snapshot date | {date} |",
        f"| Dataset commit | `{manifest.get('dataset_commit', 'unknown')}` |",
        f"| food.parquet | {_n(manifest.get('bytes', 0))} bytes, "
        f"SHA-256 `{manifest.get('sha256', 'unknown')}` |",
        f"| additives.json | {_n(taxonomy.get('bytes', 0))} bytes, "
        f"SHA-256 `{taxonomy.get('sha256', 'not present')}` |",
    ]
    if "fixture" in manifest:
        lines.append(f"| Note | {manifest['fixture']} |")
    return date, [*lines, ""]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def _dbt_section(run_results: Path) -> list[str]:
    lines = ["## dbt build", ""]
    if not run_results.exists():
        return [*lines, f"No run_results.json at `{run_results}`; run `dbt build` first.", ""]
    data = json.loads(run_results.read_text("utf-8"))
    results = data["results"]
    tests = [x for x in results if x["unique_id"].startswith("test.")]
    nodes = [x for x in results if not x["unique_id"].startswith("test.")]
    by_status: dict[str, int] = {}
    for x in tests:
        by_status[x["status"]] = by_status.get(x["status"], 0) + 1
    statuses = ", ".join(f"{k} {v}" for k, v in sorted(by_status.items()))
    meta = data.get("metadata", {})
    elapsed = data.get("elapsed_time", 0)
    lines += [
        f"dbt {meta.get('dbt_version', '?')}, finished {meta.get('generated_at', '?')[:19]}Z "
        f"in {elapsed:.0f} s.",
        "",
        f"- Models and seeds: {len(nodes)} ({sum(x['status'] == 'success' for x in nodes)} built)",
        f"- Data tests: {len(tests)} ({statuses})",
    ]
    failing = [x["unique_id"].split(".")[2] for x in tests if x["status"] != "pass"]
    if failing:
        lines += ["", "Not passing:", *[f"- `{name}`" for name in failing]]
    return [*lines, ""]


def _marts_section(r: Report) -> list[str]:
    lines = ["## Marts", "", "| Mart | Rows |", "| --- | ---: |"]
    for mart in MARTS:
        lines.append(f"| `{mart}` | {_n(r.one(f'select count(*) from {mart}'))} |")
    lines += ["", "### Null rates", ""]
    for mart in MARTS:
        columns = [
            c for (c,) in r.rows(
                "select column_name from information_schema.columns "
                f"where table_name = '{mart}' order by ordinal_position"
            )
        ]  # fmt: skip
        counts = r.con.execute(
            f"select count(*), {', '.join(f'count("{c}")' for c in columns)} from {mart}"
        ).fetchone()
        assert counts is not None
        total = counts[0]
        cells = [
            f"`{c}` {_pct(total - filled, total)}"
            for c, filled in zip(columns, counts[1:], strict=True)
        ]
        lines.append(f"- **{mart}**: " + " · ".join(cells))
    return [*lines, ""]


def _cleaning_section(r: Report) -> list[str]:
    products = r.one("select count(*) from dim_products")
    duplicates = r.one("select coalesce(sum(copies - 1), 0) from base_off__us_products")
    grades = r.rows(
        "select nutriscore_grade_raw, count(*) from stg_off__products "
        "where nutriscore_grade_raw is null or nutriscore_grade_raw not in ('a','b','c','d','e') "
        "group by 1 order by 2 desc"
    )
    capped = r.one("select count(*) from stg_off__products where completeness_raw > 1")
    unnamed = r.one("select count(*) from dim_products where name is null")
    not_gtin = r.one("select count(*) from dim_products where not gtin_valid")

    lines = [
        "## Cleaning",
        "",
        f"- US products after removing duplicate barcodes: {_n(products)} "
        f"({_n(duplicates)} duplicate rows dropped, latest kept).",
        f"- Products without a usable name: {_n(unnamed)} ({_pct(unnamed, products)}; limit 3%).",
        "- Nutri-Score values that are not grades, set to null: "
        + ", ".join(f"{g if g is not None else 'missing'} {_n(n)}" for g, n in grades)
        + ".",
        f"- Completeness above 1, capped at 1: {_n(capped)}.",
        f"- Codes that are not real GS1 barcodes (kept, never offered as swaps): {_n(not_gtin)} "
        f"({_pct(not_gtin, products)}).",
        "",
        "Impossible nutrient values blanked in `fct_nutrition` (below 0, above 100 g, "
        "or above 900 kcal per 100 g):",
        "",
        "| Nutrient | Values present | Blanked | Kept |",
        "| --- | ---: | ---: | ---: |",
    ]
    for col in NUTRIENTS:
        present, blanked = r.con.execute(
            f"select count(s.{col}), count(s.{col}) - count(f.{col}) "
            "from stg_off__nutrition s join fct_nutrition f using (code)"
        ).fetchone() or (0, 0)
        lines.append(f"| `{col}` | {_n(present)} | {_n(blanked)} | {_n(present - blanked)} |")

    entries, recognised, with_ingredients = r.con.execute(
        "select count(*), count(*) filter (where in_taxonomy), count(distinct code) "
        "from stg_off__product_ingredients"
    ).fetchone() or (0, 0, 0)
    repeats = r.one(
        "select count(*) - (select count(*) from bridge_product_ingredients) "
        "from stg_off__product_ingredients where in_taxonomy"
    )
    outside = r.rows(
        "select additive_id, product_count from dim_additives where not in_taxonomy order by 1"
    )
    lines += [
        "",
        f"- Ingredient entries: {_n(entries)} top-level entries on "
        f"{_n(with_ingredients)} products; {_n(recognised)} ({_pct(recognised, entries)}) "
        "recognised by Open Food Facts and kept, "
        f"{_n(repeats)} repeats of an ingredient already listed dropped.",
        "- Additives missing from the taxonomy (kept, named by E-number): "
        + (", ".join(f"`{a}` ({_products(n)})" for a, n in outside) or "none")
        + ".",
    ]

    tagged = r.one("select count(distinct code) from stg_off__product_categories")
    mapped = r.one("select count(category_main) from dim_products")
    lines += [
        "",
        f"Categories: {_n(mapped)} products ({_pct(mapped, products)}) get a category from "
        f"Open Food Facts tags via `category_map`; {_n(tagged)} have any tag, so "
        f"{_pct(mapped, tagged)} of tagged products are covered. The other "
        f"{_n(products - mapped)} wait for phase 3's model.",
        "",
        "| Category | Products |",
        "| --- | ---: |",
    ]
    for name, n in r.rows(
        "select c.name, count(p.code) from dim_categories c "
        "left join dim_products p on p.category_main = c.category_id "
        "where c.parent_id is not null or c.category_id in ('supplements', 'other') "
        "group by c.name order by 2 desc"
    ):
        lines.append(f"| {name} | {_n(n)} |")
    return [*lines, ""]


def build_report(db_path: Path = DB_PATH, run_results: Path = RUN_RESULTS) -> tuple[str, str]:
    """Return (snapshot date, Markdown)."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        r = Report(con)
        date, snapshot = _snapshot_section(r)
        body = [
            f"# Pipeline run report: {date}",
            "",
            f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC by `pipeline/report.py` "
            f"from `{run_results.parent.name}/run_results.json`. "
            "Contains data from Open Food Facts, available under the Open Database License.",
            "",
            *snapshot,
            *_dbt_section(run_results),
            *_marts_section(r),
            *_cleaning_section(r),
        ]
    finally:
        con.close()
    return date, "\n".join(body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the pipeline run report.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--run-results", type=Path, default=RUN_RESULTS)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args(argv)

    date, text = build_report(args.db, args.run_results)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{date}.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
