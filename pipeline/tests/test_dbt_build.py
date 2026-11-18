"""dbt build on the committed fixture: every model and data test, plus behaviour on known rows.

dbt runs once per session as a subprocess (see conftest.py and pipeline/tests/support.py),
exactly as a person runs it, into a temporary DuckDB file. The fixture is cut by
scripts/make_fixture.py and contains each cleaning case.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from pipeline.tests.support import FIXTURE_PARQUET, FIXTURE_VARS, Build, run_dbt

US = "list_contains(countries_tags, 'en:united-states')"


@pytest.fixture(scope="module")
def build(dbt_fixture: Build) -> Build:
    return dbt_fixture


@pytest.fixture(scope="module")
def con(build: Build) -> Iterator[duckdb.DuckDBPyConnection]:
    assert build.run.returncode == 0, build.run.output[-3000:]
    connection = duckdb.connect(str(build.db), read_only=True)
    yield connection
    connection.close()


def _one(con: duckdb.DuckDBPyConnection, sql: str) -> object:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_build_passes_with_at_least_30_tests(build: Build) -> None:
    assert build.run.returncode == 0, build.run.output[-3000:]
    tests = [r for r in build.run.results if r["unique_id"].startswith("test.")]
    assert len(tests) >= 30
    assert {r["status"] for r in tests} == {"pass"}


def test_one_row_per_us_barcode(con: duckdb.DuckDBPyConnection) -> None:
    raw = duckdb.connect()
    us_codes = _one(
        raw,
        f"select count(distinct code) from read_parquet('{FIXTURE_PARQUET.as_posix()}') where {US}",
    )
    assert _one(con, "select count(*) from dim_products") == us_codes
    non_us = raw.execute(
        f"select code from read_parquet('{FIXTURE_PARQUET.as_posix()}') where not {US}"
    ).fetchall()
    assert not con.execute(
        "select code from dim_products where code in (select unnest($1))",
        [[c for (c,) in non_us]],
    ).fetchall()


def test_duplicate_barcode_keeps_latest_row(con: duckdb.DuckDBPyConnection) -> None:
    raw = duckdb.connect()
    latest = raw.execute(
        f"""select code, max(last_modified_t) from read_parquet('{FIXTURE_PARQUET.as_posix()}')
            where {US} group by code having count(*) > 1"""
    ).fetchall()
    assert latest, "fixture should contain duplicate barcodes"
    for code, modified in latest:
        kept = _one(con, f"select epoch(last_modified_at) from dim_products where code = '{code}'")
        assert kept == modified


def test_impossible_nutrients_are_blanked_not_dropped(con: duckdb.DuckDBPyConnection) -> None:
    blanked = _one(
        con,
        """select count(*) from fct_nutrition f join stg_off__nutrition s using (code)
           where s.energy_kcal_100g > 900 and f.energy_kcal_100g is null""",
    )
    assert isinstance(blanked, int) and blanked > 0
    kept = _one(
        con,
        """select count(f.fat_100g) from fct_nutrition f join stg_off__nutrition s using (code)
           where s.energy_kcal_100g > 900 and s.fat_100g between 0 and 100""",
    )
    assert isinstance(kept, int) and kept > 0  # other values on the same product survive


def test_pseudo_grades_become_null(con: duckdb.DuckDBPyConnection) -> None:
    raw_unknown = _one(
        con,
        "select count(*) from stg_off__products "
        "where nutriscore_grade_raw in ('unknown', 'not-applicable')",
    )
    assert isinstance(raw_unknown, int) and raw_unknown > 0
    assert (
        _one(
            con,
            "select count(*) from dim_products where nutriscore_grade not in ('a','b','c','d','e')",
        )
        == 0
    )


def test_additives_outside_taxonomy_keep_a_row(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        "select additive_id, e_number, name from dim_additives where not in_taxonomy"
    ).fetchall()
    assert rows
    assert all(name for _, _, name in rows)


def test_names_are_clean(con: duckdb.DuckDBPyConnection) -> None:
    assert (
        _one(
            con, "select count(*) from dim_products where name like '%&quot;%' or name like '%  %'"
        )
        == 0
    )
    low_comma = chr(0x201A)  # OFF's chemical comma, restored to ',' in names
    assert _one(con, f"select count(*) from dim_ingredients where name like '%{low_comma}%'") == 0
    assert (
        _one(con, "select name from dim_additives where additive_id = 'en:e330'") == "Citric acid"
    )


def test_image_urls_follow_off_folder_rule(con: duckdb.DuckDBPyConnection) -> None:
    urls = con.execute(
        "select code, image_url from dim_products where image_url is not null"
    ).fetchall()
    assert urls
    for code, url in urls:
        folder = url.removeprefix("https://images.openfoodfacts.org/images/products/").rsplit(
            "/", 1
        )[0]
        digits = folder.replace("/", "")
        if len(code) <= 8:
            assert folder == code
        else:
            assert digits.lstrip("0") == code.lstrip("0")
            assert len(digits) == max(len(code), 13)


def test_a_tighter_threshold_fails_the_build(
    build: Build, tmp_path: Path, con: duckdb.DuckDBPyConnection
) -> None:
    """The data tests bite: demanding names on 99.9% of products must fail on the fixture.

    Runs on a copy of the built database, since this module holds the original open.
    """
    shutil.copy(build.db, tmp_path / "fixture.duckdb")
    strict = {**FIXTURE_VARS, "max_unnamed_share": 0.001}
    run = run_dbt("test", tmp_path, strict, "dim_products")
    assert run.returncode != 0
    statuses = {r["unique_id"].split(".")[2]: r["status"] for r in run.results}
    assert statuses["max_null_share_dim_products_name___var_max_unnamed_share_"] == "fail"
    others = {name: status for name, status in statuses.items() if "max_null_share" not in name}
    assert set(others.values()) == {"pass"}


def test_run_report_covers_marts_tests_and_cleaning(
    build: Build, con: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    from pipeline import report

    date, text = report.build_report(build.db, build.tmp / "target-build" / "run_results.json")

    assert date == "2026-11-17"
    assert "| Dataset commit | `05a8391172ff01006b98d911dbf553463e527057` |" in text
    for mart in report.MARTS:
        assert f"| `{mart}` |" in text
    products = _one(con, "select count(*) from dim_products")
    assert f"| `dim_products` | {products:,} |" in text
    assert "Data tests: " in text and "(pass " in text
    assert "duplicate rows dropped" in text and "3 duplicate rows dropped" in text
    assert "| `energy_kcal_100g` |" in text
    assert "Not passing" not in text
    assert "Open Database License" in text

    code = report.main(
        [
            "--db", str(build.db),
            "--run-results", str(build.tmp / "target-build" / "run_results.json"),
            "--out-dir", str(tmp_path),
        ]
    )  # fmt: skip
    assert code == 0
    assert (
        (tmp_path / "2026-11-17.md")
        .read_text("utf-8")
        .startswith("# Pipeline run report: 2026-11-17")
    )


def test_report_formats_small_shares_and_plurals() -> None:
    from pipeline import report

    assert report._pct(0, 10) == "0.0%"
    assert report._pct(1, 10_000) == "<0.1%"
    assert report._pct(1, 4) == "25.0%"
    assert report._pct(1, 0) == "n/a"
    assert report._products(1) == "1 product"
    assert report._products(2_000) == "2,000 products"


def test_the_build_runs_in_two_steps_so_ci_can_delete_the_parquet(
    build: Build, tmp_path: Path
) -> None:
    """The weekly workflow builds base_off__us_products, deletes the 8 GB food.parquet to free
    the runner's disk, then builds the rest with the snapshot folder pinned. Same nodes, same
    passing tests as one build."""
    snapshot = tmp_path / "raw" / FIXTURE_PARQUET.parent.name
    shutil.copytree(FIXTURE_PARQUET.parent, snapshot)
    vars_ = {**FIXTURE_VARS, "raw_dir": (tmp_path / "raw").as_posix()}

    first = run_dbt("build", tmp_path, vars_, "base_off__us_products", target_name="target-1")
    assert first.returncode == 0, first.output[-3000:]
    parquet = snapshot / "food.parquet"
    parquet.chmod(0o644)  # snapshots are read-only; Windows will not unlink one
    parquet.unlink()

    pinned = {**vars_, "snapshot_dir": snapshot.as_posix()}
    rest = run_dbt(
        "build", tmp_path, pinned, exclude=("base_off__us_products",), target_name="target-2"
    )
    assert rest.returncode == 0, rest.output[-3000:]

    two_steps = {r["unique_id"] for r in first.results + rest.results}
    assert two_steps == {r["unique_id"] for r in build.run.results}
    assert all(r["status"] in ("success", "pass") for r in first.results + rest.results)
