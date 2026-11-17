"""Cut the dbt test fixture from a real snapshot.

    uv run python scripts/make_fixture.py [--snapshot data/raw/2026-11-17]

Writes pipeline/tests/fixtures/raw/<date>/ with about 300 real rows of food.parquet (every
column kept, so the schema matches the export) and the additives.json entries those rows use.
Rows are chosen by case, each in a fixed hash order, so the fixture is the same on every run:

- a spread of ordinary US products, and some non-US products the US filter must drop
- every barcode that appears twice among US rows
- out-of-range nutrient values, which fct_nutrition must blank
- unknown and not-applicable Nutri-Score grades, and products with no usable name
- products using additives missing from the taxonomy

Derived from Open Food Facts, so the fixture stays under the ODbL.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_RAW = ROOT / "pipeline" / "tests" / "fixtures" / "raw"
US = "list_contains(countries_tags, 'en:united-states')"
SEED = "labellens-fixture-v1"


def _nutrient(name: str) -> str:
    return f"list_filter(nutriments, lambda x: x.name = '{name}')[1].\"100g\""


# (case name, WHERE clause, how many rows)
CASES: list[tuple[str, str, int]] = [
    ("us_ordinary", f"{US}", 170),
    ("us_with_category", f"{US} AND len(categories_tags) > 2", 40),
    ("not_us", f"NOT {US} AND countries_tags IS NOT NULL", 25),
    (
        "duplicate_code",
        f"{US} AND code IN (SELECT code FROM src WHERE {US} GROUP BY code HAVING count(*) > 1)",
        10,
    ),
    ("energy_too_high", f"{US} AND {_nutrient('energy-kcal')} > 900", 8),
    ("sugar_too_high", f"{US} AND {_nutrient('sugars')} > 100", 4),
    ("salt_too_high", f"{US} AND {_nutrient('salt')} > 100", 4),
    ("grade_unknown", f"{US} AND nutriscore_grade = 'unknown'", 8),
    ("grade_not_applicable", f"{US} AND nutriscore_grade = 'not-applicable'", 6),
    (
        "no_name",
        f"{US} AND len(list_filter(product_name, lambda x: trim(coalesce(x.text, '')) <> '')) = 0",
        10,
    ),
    (
        "additive_not_in_taxonomy",
        f"{US} AND list_has_any(additives_tags, ['en:e386', 'xx:e364'])",
        4,
    ),
]


def build(snapshot: Path, out_root: Path = FIXTURE_RAW) -> Path:
    out = out_root / snapshot.name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    source = (snapshot / "food.parquet").as_posix()
    target = (out / "food.parquet").as_posix()
    numbered = "(SELECT *, row_number() OVER () AS rowid_ FROM src)"

    con = duckdb.connect()
    con.execute(f"CREATE TEMP VIEW src AS SELECT * FROM read_parquet('{source}')")
    picks = " UNION ALL ".join(
        f"(SELECT rowid_ AS r, '{name}' AS why FROM {numbered} "
        f"WHERE {where} ORDER BY md5(code || ':{name}:{SEED}'), rowid_ LIMIT {n})"
        for name, where, n in CASES
    )
    con.execute(f"CREATE TEMP TABLE picks AS {picks}")
    for why, n in con.execute("SELECT why, count(*) FROM picks GROUP BY 1 ORDER BY 1").fetchall():
        print(f"  {why:<26} {n}")
    con.execute("CREATE TEMP TABLE picked AS SELECT DISTINCT r FROM picks")
    con.execute(
        f"""COPY (
              SELECT * EXCLUDE (rowid_) FROM {numbered}
              WHERE rowid_ IN (SELECT r FROM picked) ORDER BY code, rowid_
            ) TO '{target}' (FORMAT parquet, COMPRESSION zstd)"""
    )

    used = {
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT unnest(additives_tags) FROM read_parquet('{target}')"
        ).fetchall()
    }
    taxonomy = json.loads((snapshot / "additives.json").read_text("utf-8"))
    trimmed = {k: v for k, v in sorted(taxonomy.items()) if k in used}
    (out / "additives.json").write_text(json.dumps(trimmed, indent=1, ensure_ascii=False), "utf-8")

    manifest = json.loads((snapshot / "manifest.json").read_text("utf-8"))
    manifest["fixture"] = (
        f"Rows cut by scripts/make_fixture.py with seed {SEED}; not the full file."
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")

    counts = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE {US}) FROM read_parquet('{target}')"
    ).fetchone()
    assert counts is not None
    print(f"Fixture: {counts[0]} rows ({counts[1]} US), {len(trimmed)} taxonomy entries -> {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut the dbt test fixture from a snapshot.")
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data" / "raw" / "2026-11-17")
    args = parser.parse_args(argv)
    build(args.snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
