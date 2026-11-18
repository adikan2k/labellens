"""The label-reading eval's scoring, the audit's effect on it, and that nothing is sent
without --yes."""

from __future__ import annotations

from typing import Any

import pytest

from evals.datasets.build_labels import image_folder, image_url
from evals.runners import label_eval
from evals.runners.label_eval import family, nutrient_right, run_key, score, truth_of

NUTRITION = {
    "energy_kcal_100g": 400.0,
    "sugars_100g": 20.0,
    "salt_100g": 1.0,
    "fat_100g": 10.0,
    "saturated_fat_100g": 2.0,
    "fiber_100g": 0.0,
    "proteins_100g": 8.0,
}


def item(item_id: str = "label-01", **truth: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "code": "0000000000017",
        "name": "Oat Squares",
        "brand": "Zorblax",
        "category": "breakfast-cereals",
        "language": "en",
        "images": [],
        "truth": {"nutrition": NUTRITION | truth.get("nutrition", {}), "additives": ["en:e322i"]},
    }


def run(**printed: float | None) -> dict[str, Any]:
    """A cached read: per 100 g values as printed, the rest not printed."""
    keys = ("energy_kcal", "energy_kj", "fat_g", "saturated_fat_g", "sodium_mg", "salt_g",
            "fiber_g", "sugars_g", "protein_g")  # fmt: skip
    return {
        "reading": {
            "is_food_label": True,
            "name": "Oat Squares",
            "brand": "Zorblax",
            "barcode": None,
            "basis": "per_100g",
            "serving_size_g": None,
            "nutrition": {k: printed.get(k) for k in keys},
            "ingredients": ["oats"],
            "additives": [],
            "category_id": "breakfast-cereals",
        }
    }


RIGHT = {"energy_kcal": 405, "fat_g": 10, "saturated_fat_g": 2, "salt_g": 1.0,
         "sugars_g": 21, "protein_g": 8}  # fmt: skip


def test_a_value_is_right_within_ten_percent_or_a_small_absolute_margin() -> None:
    assert nutrient_right("sugars_100g", 21.9, 20.0)
    assert not nutrient_right("sugars_100g", 22.5, 20.0)
    assert nutrient_right("fat_100g", 0.4, 0.0)  # within 0.5 g
    assert nutrient_right("salt_100g", 0.08, 0.0) and not nutrient_right("salt_100g", 0.2, 0.0)
    assert nutrient_right("energy_kcal_100g", 8.0, 0.0)  # within 10 kcal
    assert not nutrient_right("fat_100g", None, 5.0)


def test_additives_compare_by_e_number_family() -> None:
    assert family("en:e322i") == family("en:e322") == "322"
    assert family("en:e160a") == "160"
    assert family("en:vanillin") is None


def test_as_is_a_nutrient_the_label_does_not_print_counts_as_a_miss() -> None:
    summary = score([item()], [run(**RIGHT)], [{"322"}])
    assert summary["nutrients_known"] == 7 and summary["nutrients_right"] == 6
    assert summary["labels_all_right"] == 0  # fiber: truth 0, nothing read
    assert summary["additives"] == {"true_positive": 1, "predicted": 1, "actual": 1}


def test_checked_it_is_not_scored_and_corrections_and_exclusions_apply() -> None:
    items = [item("label-01"), item("label-02"), item("label-03")]
    wrong_truth = run(**(RIGHT | {"energy_kcal": 744}))
    runs = [run(**RIGHT), wrong_truth, run()]
    audit = {
        "label-02": {"nutrition": {"energy_kcal_100g": 744}, "additives": []},
        "label-03": {"exclude": "The photo is of another product."},
    }
    summary = score(items, runs, [{"322"}, {"330"}, set()], audit)
    assert summary["labels"] == 2 and summary["labels_all_right"] == 2
    assert summary["not_printed"] == 2  # fiber, twice
    assert summary["nutrients_known"] == 12 and summary["nutrients_right"] == 12
    assert [e["id"] for e in summary["excluded"]] == ["label-03"]
    # label-02's corrected truth has no additives, so the E330 found there is a false positive.
    assert summary["additives"] == {"true_positive": 1, "predicted": 2, "actual": 1}
    assert truth_of(items[1], audit)[0]["energy_kcal_100g"] == 744


def test_a_failed_read_scores_every_value_wrong() -> None:
    summary = score([item()], [{"reading": None}], [set()])
    assert summary["nutrients_right"] == 0 and summary["read_as_food"] == 0


def test_the_cache_key_changes_with_the_prompt_the_model_and_the_photos() -> None:
    base = run_key("claude-haiku-5-5", "label-v1", [b"a", b"b"])
    assert base == run_key("claude-haiku-5-5", "label-v1", [b"a", b"b"])
    assert base != run_key("claude-haiku-5-5", "label-v2", [b"a", b"b"])
    assert base != run_key("claude-sonnet-5-5", "label-v1", [b"a", b"b"])
    assert base != run_key("claude-haiku-5-5", "label-v1", [b"a", b"c"])


def test_nothing_is_sent_without_yes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(label_eval, "photos_of", lambda _: [b"\xff\xd8\xff photo"])

    def no_client() -> Any:
        raise AssertionError("a client was built without --yes")

    runs = label_eval.read_all(
        [item()],
        client_factory=no_client,
        model="claude-haiku-5-5",
        cache=label_eval.RunCache(tmp_path / "runs.jsonl"),
        prices=(0.10, 0.50),
        yes=False,
    )
    out = capsys.readouterr().out
    assert runs is None
    assert "1 to read" in out and "at most $" in out and "Nothing sent" in out


def test_image_urls_follow_open_food_facts_folders() -> None:
    assert image_folder("0898999000503") == "089/899/900/0503"
    assert image_folder("20005832") == "20005832"
    assert image_folder("016000275287") == "001/600/027/5287"
    assert image_url("0898999000503", "nutrition_en", 238).endswith(
        "/089/899/900/0503/nutrition_en.238.full.jpg"
    )
