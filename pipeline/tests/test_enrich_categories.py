"""The category task: prompt, validation and inputs (no paid calls)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.enrich import categories, core
from pipeline.tests.fake_anthropic import FakeAnthropic
from pipeline.tests.support import Build


def test_every_leaf_category_has_a_guide_line_and_parents_are_not_offered() -> None:
    task = categories.CategoryTask()
    assert len(task.leaves) == 26
    assert set(task.leaves) == set(categories.GUIDE)
    assert "drinks" not in task.leaves and "other" in task.leaves
    for category_id in task.leaves:
        assert f"- {category_id} (" in task.system()


def test_answers_must_be_a_listed_category() -> None:
    task = categories.CategoryTask()
    assert task.parse_item({}, {"id": 1, "category": "cheese"}) == "cheese"
    for bad in ("dairy", "Cheese", "", None):
        with pytest.raises(core.InvalidOutput):
            task.parse_item({}, {"id": 1, "category": bad})


def test_the_schema_limits_answers_to_leaf_ids() -> None:
    task = categories.CategoryTask()
    assert task.item_schema()["category"]["enum"] == list(task.leaves)


def test_payload_leaves_out_empty_fields_and_tidies_spaces() -> None:
    assert categories.payload("  Honey  Nut Cheerios ", " General Mills", None) == {
        "name": "Honey Nut Cheerios",
        "brand": "General Mills",
    }
    assert categories.payload("Cola", "", "carbonated water,  sugar") == {
        "name": "Cola",
        "ingredients": "carbonated water, sugar",
    }


def test_user_message_numbers_products_and_labels_fields() -> None:
    message = categories.CategoryTask().user_message(
        [{"name": "Cola", "brand": "Acme"}, {"name": "Oat milk", "ingredients": "oats, water"}]
    )
    assert message.splitlines() == [
        "1. name: Cola | brand: Acme",
        "2. name: Oat milk | ingredients: oats, water",
    ]


def test_items_come_from_the_dbt_inputs_untagged_first_by_scans(dbt_fixture: Build) -> None:
    import duckdb

    items = categories.load_items(dbt_fixture.db)
    with duckdb.connect(str(dbt_fixture.db), read_only=True) as con:
        untagged = con.execute(
            "select count(*) from int_category_inputs where tag_category is null"
        ).fetchone()
        tagged_codes = {
            c
            for (c,) in con.execute(
                "select code from int_category_inputs where tag_category is not null"
            ).fetchall()
        }
    assert untagged and len(items) == untagged[0]
    assert not tagged_codes & {i.ref for i in items}
    every = categories.load_items(dbt_fixture.db, untagged_only=False)
    assert len(every) > len(items)
    name_only = categories.load_items(dbt_fixture.db, untagged_only=False, name_only=True)
    assert all("ingredients" not in i.payload for i in name_only)
    assert any("ingredients" in i.payload for i in every)


def test_a_fill_run_stores_one_category_per_product(
    dbt_fixture: Build, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core, "STATE_DIR", tmp_path / "state")
    task = categories.CategoryTask()

    def answer(params: dict) -> str:
        count = len(params["messages"][0]["content"].splitlines())
        return json.dumps({"items": [{"id": n, "category": "other"} for n in range(1, count + 1)]})

    items = categories.load_items(dbt_fixture.db)
    client = FakeAnthropic(answer)
    summary = core.run(
        task,
        items,
        client_factory=lambda: client,
        settings=core.CallSettings("model-x", thinking_off=True),
        store=core.OutputStore(tmp_path / "categories.parquet"),
        prices=(0.1, 0.5),
        limit=10_000,
        yes=True,
        batch=True,
        prune=True,
        poll_seconds=0,
        log=lambda _: None,
    )
    rows = core.OutputStore(tmp_path / "categories.parquet").load()
    assert summary.errored == 0 and len(rows) == len(items)
    assert {r["ref"] for r in rows} == {i.ref for i in items}
