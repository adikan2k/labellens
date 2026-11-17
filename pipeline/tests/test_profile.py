"""Profile tests on a small Parquet fixture with strings, lists, structs, nulls and empties."""

from pathlib import Path

import duckdb
import pytest

from pipeline.ingest import profile as prof

US = "list_contains(countries_tags, 'en:united-states')"


@pytest.fixture
def parquet(tmp_path: Path) -> Path:
    path = tmp_path / "food.parquet"
    duckdb.execute(
        f"""
        COPY (
          SELECT * FROM (VALUES
            ('0001', 'Corn flakes', ['en:united-states'], {{'lang': 'en', 'text': 'a'}}, 'b'),
            ('0002', '',            ['en:united-states'], NULL,                         NULL),
            ('0003', NULL,          ['en:france'],        {{'lang': 'fr', 'text': 'b'}}, 'a'),
            ('0004', 'Chips | salt',['en:united-states', 'en:canada'], NULL,            'e'),
            ('0005', 'Gâteau',      [],                   NULL,                         'c')
          ) AS t(code, product_name, countries_tags, label, nutriscore_grade)
        ) TO '{path.as_posix()}' (FORMAT parquet)
        """
    )
    return path


def test_candidates_find_country_columns(parquet: Path) -> None:
    found = prof.find_candidates(prof.connect(), parquet)

    assert [c.name for c in found] == ["countries_tags"]
    assert found[0].matching_rows == 3
    assert ("en:united-states", 3) in found[0].top_values


def test_profile_counts_rows_and_rates(parquet: Path) -> None:
    profile = prof.build_profile(prof.connect(), parquet, US, sample_rows=100)
    cols = {c.name: c for c in profile.columns}

    assert profile.rows == 5
    assert profile.us_rows == 3
    assert cols["product_name"].null_all == pytest.approx(20.0)
    assert cols["product_name"].null_us == pytest.approx(0.0)
    assert cols["product_name"].empty_all == pytest.approx(20.0)
    assert cols["product_name"].empty_us == pytest.approx(100 / 3)
    assert cols["countries_tags"].empty_all == pytest.approx(20.0)
    assert cols["label"].empty_all is None  # structs have no notion of empty
    assert cols["nutriscore_grade"].null_us == pytest.approx(100 / 3)


def test_samples_come_from_us_rows_only_and_skip_empties(parquet: Path) -> None:
    profile = prof.build_profile(prof.connect(), parquet, US, sample_rows=100)
    names = next(c for c in profile.columns if c.name == "product_name").samples

    assert "Gâteau" not in names  # not a US row
    assert "" not in names
    assert set(names) == {"Corn flakes", "Chips \\| salt"}


def test_samples_are_most_common_first(parquet: Path) -> None:
    profile = prof.build_profile(prof.connect(), parquet, US, sample_rows=100)
    tags = next(c for c in profile.columns if c.name == "countries_tags").samples

    # ['en:united-states'] appears twice among US rows, the two-country list once.
    assert tags[0] == "['en:united-states']"


def test_render_writes_header_and_one_row_per_column(parquet: Path) -> None:
    profile = prof.build_profile(prof.connect(), parquet, US, sample_rows=100)
    manifest = {"snapshot_date": "2026-11-17", "bytes": 1234, "dataset_commit": "abc"}

    text = prof.render(profile, manifest, "cmd")

    assert "| US rows | 3 (60.0% of rows) |" in text
    assert f"| US filter | `{US}` |" in text
    assert "| File size | 1,234 bytes |" in text
    table_rows = [line for line in text.splitlines() if line.startswith("| `")]
    assert len(table_rows) == 5


def test_long_samples_are_cut() -> None:
    cleaned = prof._clean("x" * 200)
    assert len(cleaned) == prof.SAMPLE_WIDTH
    assert cleaned.endswith("…")


def test_latest_snapshot_picks_newest_date(tmp_path: Path) -> None:
    for day in ["2026-11-01", "2026-11-17", "2026-10-30"]:
        (tmp_path / day).mkdir()
        (tmp_path / day / "food.parquet").write_bytes(b"")

    assert prof.latest_snapshot(tmp_path).parent.name == "2026-11-17"
