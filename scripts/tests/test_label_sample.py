"""The sampler on a Parquet fixture shaped like the real export (see docs/data-profile.md)."""

import csv
from pathlib import Path

import duckdb
import pytest

from scripts import label as labeller

ROWS = """
  ('001', [{'lang': 'main', 'text': 'Main name'}, {'lang': 'en', 'text': 'English name'}],
   'Acme', [{'lang': 'main', 'text': 'corn,' || chr(13) || chr(10) || ' sugar'}],
   ['en:united-states'], 10),
  ('002', [{'lang': 'fr', 'text': 'Nom'}, {'lang': 'en', 'text': 'English only'}],
   NULL, [{'lang': 'en', 'text': 'water'}], ['en:united-states', 'en:canada'], 10),
  ('003', [{'lang': 'main', 'text': 'French product'}],
   'Marque', [{'lang': 'main', 'text': 'lait'}], ['en:france'], 10),
  ('004', [{'lang': 'main', 'text': '   '}],
   'Blank', [{'lang': 'main', 'text': 'salt'}], ['en:united-states'], 10),
  ('005', [{'lang': 'main', 'text': 'No ingredients'}],
   'Acme', [], ['en:united-states'], 10),
  ('006', [{'lang': 'main', 'text': 'Old row'}],
   'Acme', [{'lang': 'main', 'text': 'old'}], ['en:united-states'], 1),
  ('006', [{'lang': 'main', 'text': 'New row'}],
   'Acme', [{'lang': 'main', 'text': 'new'}], ['en:united-states'], 2)
"""


@pytest.fixture
def parquet(tmp_path: Path) -> Path:
    path = tmp_path / "food.parquet"
    duckdb.connect().execute(
        f"""COPY (SELECT * FROM (VALUES {ROWS})
              AS t(code, product_name, brands, ingredients_text, countries_tags, last_modified_t))
            TO '{path.as_posix()}' (FORMAT parquet)"""
    )
    return path


def _draw(parquet: Path, tmp_path: Path, **kwargs: object) -> list[dict[str, str]]:
    out = tmp_path / "sample.csv"
    labeller.draw_sample(parquet, out, "2026-11-17", **kwargs)  # type: ignore[arg-type]
    return list(csv.DictReader(out.open(encoding="utf-8")))


def test_sample_keeps_only_us_products_with_name_and_ingredients(
    parquet: Path, tmp_path: Path
) -> None:
    codes = {r["code"] for r in _draw(parquet, tmp_path)}
    assert codes == {"001", "002", "006"}


def test_text_prefers_main_then_english(parquet: Path, tmp_path: Path) -> None:
    rows = {r["code"]: r for r in _draw(parquet, tmp_path)}

    assert rows["001"]["name"] == "Main name"
    assert rows["001"]["ingredients"] == "corn, sugar"  # line breaks collapsed
    assert rows["002"]["name"] == "English only"
    assert rows["002"]["brand"] == ""
    assert rows["001"]["snapshot_date"] == "2026-11-17"


def test_duplicate_barcode_keeps_latest_row(parquet: Path, tmp_path: Path) -> None:
    rows = {r["code"]: r for r in _draw(parquet, tmp_path)}
    assert rows["006"]["name"] == "New row"


def test_sample_is_deterministic_and_respects_size(parquet: Path, tmp_path: Path) -> None:
    first = [r["code"] for r in _draw(parquet, tmp_path, size=2)]
    second = [r["code"] for r in _draw(parquet, tmp_path, size=2)]
    other_seed = [r["code"] for r in _draw(parquet, tmp_path, size=3, seed="another")]

    assert first == second
    assert len(first) == 2
    assert sorted(other_seed) == ["001", "002", "006"]


def test_us_filter_matches_the_data_profile() -> None:
    profile = (labeller.ROOT / "docs" / "data-profile.md").read_text(encoding="utf-8")
    assert f"| US filter | `{labeller.US_FILTER}` |" in profile


def test_sample_fields_fit_the_labeller(parquet: Path, tmp_path: Path) -> None:
    out = tmp_path / "sample.csv"
    labeller.draw_sample(parquet, out, "2026-11-17")
    products = labeller.load_sample(out)
    assert {p.code for p in products} == {"001", "002", "006"}
