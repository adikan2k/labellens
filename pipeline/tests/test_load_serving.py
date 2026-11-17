"""The serving loader, end to end on the fixture against the test Postgres."""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import duckdb
import psycopg
import pytest
import yaml

from pipeline.load import serving
from pipeline.tests.support import Build

ROOT = Path(__file__).resolve().parents[2]
IMAGE_BASE = "https://images.openfoodfacts.org/images/products/"


@pytest.fixture(scope="module")
def pg(serving_url: str) -> Iterator[psycopg.Connection]:
    # Autocommit: an idle open transaction would hold locks and block the reload's schema swap.
    with psycopg.connect(serving_url, autocommit=True) as connection:
        connection.execute("set search_path = serving")
        yield connection


@pytest.fixture(scope="module")
def marts(dbt_fixture: Build) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(dbt_fixture.db), read_only=True)
    yield connection
    connection.close()


def test_every_named_product_is_loaded_in_rank_order(
    pg: psycopg.Connection, marts: duckdb.DuckDBPyConnection
) -> None:
    named = marts.execute("select count(*) from dim_products where name is not null").fetchone()
    loaded = pg.execute("select count(*), min(rank_pos), max(rank_pos) from products").fetchone()
    assert named and loaded
    assert loaded == (named[0], 1, named[0])
    assert pg.execute("select count(*) from products where name is null").fetchone() == (0,)


def _us_barcode(code: str) -> bool:
    """GS1 prefixes 000-139 are assigned to the US and Canada (UPC-A, or EAN-13 with a 0)."""
    return len(code) in (12, 13) and int(code.zfill(13)[:3]) <= 139


def test_us_barcodes_then_english_then_scans(
    pg: psycopg.Connection, marts: duckdb.DuckDBPyConnection
) -> None:
    lang = dict(marts.execute("select code, lang from dim_products").fetchall())
    ordered = pg.execute("select code, scans from products order by rank_pos").fetchall()
    keys = [(_us_barcode(code), lang[code] == "en") for code, _ in ordered]
    assert keys == sorted(keys, reverse=True), "a US barcode ranks below an imported one"
    assert any(us for us, _ in keys) and not all(us for us, _ in keys), "fixture covers both"
    top_group = [s for (code, s) in ordered if _us_barcode(code) and lang[code] == "en"]
    assert top_group == sorted(top_group, reverse=True)


def test_arrays_keep_label_and_e_number_order(
    pg: psycopg.Connection, marts: duckdb.DuckDBPyConnection
) -> None:
    row = pg.execute(
        "select code, ingredient_ids, additive_ids from products "
        "where cardinality(ingredient_ids) > 3 and cardinality(additive_ids) > 2 limit 1"
    ).fetchone()
    assert row, "fixture should have a product with several ingredients and additives"
    code, ingredient_ids, additive_ids = row
    expected = [
        i
        for (i,) in marts.execute(
            "select ingredient_id from bridge_product_ingredients where code = ? order by rank",
            [code],
        ).fetchall()
    ]
    assert ingredient_ids == expected
    numbers = [
        int("".join(ch for ch in a.split(":e")[-1] if ch.isdigit()) or 0) for a in additive_ids
    ]
    assert numbers == sorted(numbers)


def test_image_path_rebuilds_the_mart_url(
    pg: psycopg.Connection, marts: duckdb.DuckDBPyConnection
) -> None:
    urls = dict(
        marts.execute("select code, image_url from dim_products where name is not null").fetchall()
    )
    rows = pg.execute("select code, image_path from products").fetchall()
    for code, path in rows:
        rebuilt = f"{IMAGE_BASE}{path}.400.jpg" if path else None
        assert rebuilt == urls[code]


def test_stats_document_matches_the_contract(pg: psycopg.Connection) -> None:
    spec = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text("utf-8"))
    required = set(spec["components"]["schemas"]["StatsOverview"]["required"]) - {"source"}
    row = pg.execute("select doc from stats").fetchone()
    assert row
    doc = row[0]
    assert set(doc) == required
    assert sum(item["count"] for item in doc["nutriscore"]) == doc["product_count"]
    assert sum(item["count"] for item in doc["nova"]) == doc["product_count"]
    assert doc["named_product_count"] <= doc["product_count"]
    assert doc["category_count"] == 26


def test_meta_names_the_snapshot(pg: psycopg.Connection) -> None:
    meta = dict(pg.execute("select key, value from meta").fetchall())
    assert meta["snapshot_date"] == "2026-11-17"
    assert meta["dataset_commit"] == "05a8391172ff01006b98d911dbf553463e527057"


def test_lookups_are_loaded(pg: psycopg.Connection, marts: duckdb.DuckDBPyConnection) -> None:
    for table, mart in (("additives", "dim_additives"), ("ingredients", "dim_ingredients"),
                        ("categories", "dim_categories")):  # fmt: skip
        expected = marts.execute(f"select count(*) from {mart}").fetchone()
        assert pg.execute(f"select count(*) from {table}").fetchone() == expected  # type: ignore[arg-type]
    assert pg.execute(
        "select name, function from additives where additive_id = 'en:e330'"
    ).fetchone() == ("Citric acid", "Antioxidant, sequestrant")


def test_reload_swaps_in_place(serving_url: str, dbt_fixture: Build) -> None:
    before = _count(serving_url)
    serving.load(dbt_fixture.db, serving_url, log=lambda *_: None)
    assert _count(serving_url) == before
    with psycopg.connect(serving_url) as pg:
        schemas = {s for (s,) in pg.execute("select nspname from pg_namespace").fetchall()}
    assert serving.SCHEMA in schemas
    assert not {serving.NEXT, serving.OLD} & schemas


def test_a_reader_on_the_old_tables_does_not_block_the_swap(
    serving_url: str, dbt_fixture: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serving, "SWAP_LOCK_TIMEOUT", "1s")
    messages: list[str] = []
    with psycopg.connect(serving_url) as reader:  # not autocommit: holds its lock until rollback
        reader.execute("select 1 from serving.products limit 1").fetchall()
        started = time.perf_counter()
        serving.load(dbt_fixture.db, serving_url, log=messages.append)
        assert time.perf_counter() - started < 60
        reader.rollback()
    assert any("still being read" in m for m in messages)
    assert _count(serving_url) > 0  # the new tables are live
    assert serving.OLD in _schemas(serving_url)

    serving.load(dbt_fixture.db, serving_url, log=lambda *_: None)  # cleans up the leftover
    assert serving.OLD not in _schemas(serving_url)


def test_size_guard_stops_before_connecting(
    dbt_fixture: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serving, "MAX_LOAD_BYTES", 1)
    with pytest.raises(SystemExit, match="over the"):
        # An unreachable URL proves no connection is attempted.
        serving.load(dbt_fixture.db, "postgresql://nobody@127.0.0.1:1/none", log=lambda *_: None)


def test_database_cap_needs_replace(
    serving_url: str, dbt_fixture: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(serving, "MAX_DATABASE_BYTES", 1)
    with pytest.raises(SystemExit, match="--replace"):
        serving.load(dbt_fixture.db, serving_url, log=lambda *_: None)
    assert _count(serving_url) > 0  # the live tables are untouched
    serving.load(dbt_fixture.db, serving_url, replace=True, log=lambda *_: None)
    assert _count(serving_url) > 0


def test_estimate_is_an_upper_bound(serving_url: str, dbt_fixture: Build) -> None:
    with duckdb.connect(str(dbt_fixture.db), read_only=True) as con:
        est = serving.estimate(con)
    with psycopg.connect(serving_url) as pg:
        actual = pg.execute("select pg_total_relation_size('serving.products')").fetchone()
    assert actual
    product_estimate = sum(v for k, v in est.tables.items() if k.startswith("products"))
    assert product_estimate >= actual[0]


def _schemas(url: str) -> set[str]:
    with psycopg.connect(url) as pg:
        return {s for (s,) in pg.execute("select nspname from pg_namespace").fetchall()}


def _count(url: str) -> int:
    with psycopg.connect(url) as pg:
        row = pg.execute("select count(*) from serving.products").fetchone()
    assert row
    return row[0]
