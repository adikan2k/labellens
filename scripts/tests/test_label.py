import csv
import io
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from scripts import label as labeller

CATEGORIES = """category_id,name,parent_id
snacks,Snacks,
chips,Chips and crisps,snacks
cereal,Breakfast cereals,
other,Other or unclear,
"""


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path, Path]:
    categories = tmp_path / "dim_categories.csv"
    categories.write_text(CATEGORIES, encoding="utf-8")
    sample = tmp_path / "category_sample.csv"
    with sample.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=labeller.SAMPLE_FIELDS)
        writer.writeheader()
        for code, name in [("001", "Corn flakes"), ("002", "Potato chips"), ("003", "Mystery")]:
            writer.writerow(
                {
                    "code": code,
                    "name": name,
                    "brand": "Acme",
                    "ingredients": "corn, sugar, salt",
                    "snapshot_date": "2026-11-17",
                }
            )
    return sample, categories, tmp_path / "category_gold.csv"


def _answers(*values: str) -> Callable[[str], str]:
    it: Iterator[str] = iter(values)

    def ask(_prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return ask


def _run(files: tuple[Path, Path, Path], *answers: str) -> tuple[int, str]:
    sample, categories, gold = files
    out = io.StringIO()
    code = labeller.label(sample, categories, gold, ask=_answers(*answers), out=out)
    return code, out.getvalue()


def _gold(files: tuple[Path, Path, Path]) -> list[tuple[str, str]]:
    gold = files[2]
    if not gold.exists():
        return []
    return [(r["code"], r["category_id"]) for r in csv.DictReader(gold.open(encoding="utf-8"))]


def test_only_leaf_categories_are_offered(files: tuple[Path, Path, Path]) -> None:
    names = [c.name for c in labeller.load_categories(files[1])]
    assert names == ["Chips and crisps", "Breakfast cereals", "Other or unclear"]


def test_labels_are_saved_one_by_one(files: tuple[Path, Path, Path]) -> None:
    code, out = _run(files, "2", "1", "3")

    assert code == 0
    assert _gold(files) == [("001", "cereal"), ("002", "chips"), ("003", "other")]
    assert "All 3 products labelled" in out


def test_quit_then_resume_at_next_product(files: tuple[Path, Path, Path]) -> None:
    _, out = _run(files, "2", "q")
    assert "Stopped at 1 of 3" in out
    assert _gold(files) == [("001", "cereal")]

    _, out = _run(files, "1", "q")
    assert "[2/3]  barcode 002" in out
    assert _gold(files) == [("001", "cereal"), ("002", "chips")]


def test_end_of_input_quits_safely(files: tuple[Path, Path, Path]) -> None:
    code, out = _run(files, "2")

    assert code == 0
    assert "Stopped at 1 of 3" in out


def test_undo_removes_last_label_and_shows_it_again(files: tuple[Path, Path, Path]) -> None:
    _, out = _run(files, "2", "1", "u", "3", "q")

    assert "Undid label for 002" in out
    assert out.count("barcode 002") == 2
    assert _gold(files) == [("001", "cereal"), ("002", "other")]


def test_undo_with_nothing_labelled(files: tuple[Path, Path, Path]) -> None:
    _, out = _run(files, "u", "q")
    assert "Nothing to undo." in out


@pytest.mark.parametrize("bad", ["0", "4", "abc", "", "1.5"])
def test_invalid_input_is_rejected(files: tuple[Path, Path, Path], bad: str) -> None:
    _, out = _run(files, bad, "q")

    assert "Type a number from 1 to 3, u or q." in out
    assert _gold(files) == []


def test_off_category_is_never_shown(files: tuple[Path, Path, Path]) -> None:
    _, out = _run(files, "q")
    assert "categories_tags" not in out
    assert "Corn flakes" in out and "Acme" in out and "corn, sugar, salt" in out


def test_refuses_gold_rows_from_another_sample(files: tuple[Path, Path, Path]) -> None:
    files[2].write_text("code,category_id,labelled_at\n999,cereal,x\n", encoding="utf-8")

    code, out = _run(files, "q")

    assert code == 1
    assert "not in the sample" in out


def test_refuses_labels_outside_the_taxonomy(files: tuple[Path, Path, Path]) -> None:
    files[2].write_text("code,category_id,labelled_at\n001,drinks,x\n", encoding="utf-8")

    code, out = _run(files, "q")

    assert code == 1
    assert "not in the taxonomy" in out
