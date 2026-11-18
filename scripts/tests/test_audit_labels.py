"""The blind label check: a fixed 30-product draw, and the comparison."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts import audit_labels, label


def _write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_the_draw_is_a_fixed_subset_of_the_sample(tmp_path: Path) -> None:
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    audit_labels.draw(out=first)
    audit_labels.draw(out=second)
    assert first.read_text("utf-8") == second.read_text("utf-8")
    sample = {r["code"] for r in csv.DictReader(label.SAMPLE_PATH.open(encoding="utf-8"))}
    drawn = [r["code"] for r in csv.DictReader(first.open(encoding="utf-8"))]
    assert len(drawn) == 30 and len(set(drawn)) == 30 and set(drawn) <= sample


def test_compare_counts_agreement_and_lists_the_rest(tmp_path: Path) -> None:
    fields = ["code", "category_id", "labelled_at"]
    silver, human = tmp_path / "silver.csv", tmp_path / "human.csv"
    _write(silver, [
        {"code": "1", "category_id": "cheese", "labelled_at": ""},
        {"code": "2", "category_id": "milk", "labelled_at": ""},
        {"code": "3", "category_id": "sodas", "labelled_at": ""},
    ], fields)  # fmt: skip
    _write(human, [
        {"code": "1", "category_id": "cheese", "labelled_at": ""},
        {"code": "2", "category_id": "yogurt", "labelled_at": ""},
    ], fields)  # fmt: skip
    assert audit_labels.compare(silver, human) == (1, 2, [("2", "milk", "yogurt")])
