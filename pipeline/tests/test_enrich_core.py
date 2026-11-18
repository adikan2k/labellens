"""The enrichment core against a fake client: caching, the cost guard, retries, batches."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pipeline.enrich import core
from pipeline.tests.fake_anthropic import FakeAnthropic

PRICES = (0.10, 0.50)


class Shout:
    """Answer: the word in capitals. Validation rejects anything else."""

    name = "shout"
    prompt_version = "shout-v1"
    group_size = 3
    max_tokens = 500
    output_tokens_per_item = 5

    def system(self) -> str:
        return "Return each word in capitals."

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        return "\n".join(f"{n}. {p['word']}" for n, p in enumerate(payloads, start=1))

    def item_schema(self) -> dict[str, Any]:
        return {"value": {"type": "string"}}

    def parse_item(self, payload: dict[str, Any], answer: dict[str, Any]) -> str:
        if answer["value"] != payload["word"].upper():
            raise core.InvalidOutput(answer["value"])
        return answer["value"]


def shouter(wrong: dict[str, int] | None = None):
    """An answer function; `wrong[word]` is how many times to answer that word badly."""
    wrong = dict(wrong or {})
    seen: Counter[str] = Counter()

    def answer(params: dict[str, Any]) -> str:
        items = []
        for line in params["messages"][0]["content"].splitlines():
            number, word = line.split(". ", 1)
            seen[word] += 1
            value = "nope" if seen[word] <= wrong.get(word, 0) else word.upper()
            items.append({"id": int(number), "value": value})
        return json.dumps({"items": items})

    return answer


def run(
    client: FakeAnthropic,
    store_path: Path,
    words: list[str],
    refs: list[str] | None = None,
    **kwargs: Any,
) -> core.Summary:
    options: dict[str, Any] = {"limit": 1000, "yes": True, "batch": False, "log": lambda _: None}
    options.update(kwargs)
    return core.run(
        Shout(),
        [core.Item(ref=r, payload={"word": w}) for r, w in zip(refs or words, words, strict=True)],
        client_factory=lambda: client,
        settings=core.CallSettings(model="model-x", thinking_off=True),
        store=core.OutputStore(store_path),
        prices=PRICES,
        poll_seconds=0,
        **options,
    )


@pytest.fixture(autouse=True)
def _state_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(core, "STATE_DIR", tmp_path / "state")


WORDS = ["apple", "pear", "fig", "kiwi", "plum"]


@pytest.mark.parametrize("suffix", [".jsonl", ".parquet"])
def test_a_second_run_makes_no_calls(tmp_path: Path, suffix: str) -> None:
    client = FakeAnthropic(shouter())
    first = run(client, tmp_path / f"out{suffix}", WORDS)
    assert first.ok == 5 and len(client.calls) == 2  # 3 + 2 items per request

    second = run(client, tmp_path / f"out{suffix}", WORDS)
    assert second.cached == 5 and second.uncached == 0
    assert second.estimate is None and not second.sent
    assert len(client.calls) == 2  # nothing new
    assert second.cost == 0


def test_nothing_is_sent_without_yes_but_the_estimate_is_printed(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    lines: list[str] = []
    summary = run(client, tmp_path / "out.jsonl", WORDS, yes=False, log=lines.append)
    assert client.calls == [] and not summary.sent
    assert summary.estimate and summary.estimate.items == 5 and summary.estimate.requests == 2
    assert any("about $" in line for line in lines)
    assert any("--yes" in line for line in lines)
    assert not (tmp_path / "out.jsonl").exists()


def test_limit_caps_the_items_sent(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    summary = run(client, tmp_path / "out.jsonl", WORDS, limit=2)
    assert summary.ok == 2 and summary.uncached == 5
    assert run(client, tmp_path / "out.jsonl", WORDS, limit=10).ok == 3  # the rest


def test_invalid_output_is_retried_once_then_stored_as_null(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter({"fig": 1, "kiwi": 5}))  # fig recovers, kiwi never does
    summary = run(client, tmp_path / "out.jsonl", WORDS)
    assert (summary.ok, summary.invalid) == (4, 1)
    assert len(client.calls) == 3  # two first-attempt requests, one retry with fig and kiwi
    rows = core.OutputStore(tmp_path / "out.jsonl").load()
    by_ref = {r["ref"]: r for r in rows}
    assert by_ref["fig"]["value"] == "FIG"
    assert by_ref["kiwi"]["value"] is None and by_ref["kiwi"]["status"] == "invalid"
    # Stored as invalid, so a rerun does not pay for kiwi again.
    assert run(client, tmp_path / "out.jsonl", WORDS).uncached == 0


def test_batch_results_are_matched_by_custom_id_not_order(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())  # the fake returns batch results in reverse order
    summary = run(client, tmp_path / "out.jsonl", WORDS, batch=True)
    assert summary.ok == 5 and client.batches_created == 1
    rows = core.OutputStore(tmp_path / "out.jsonl").load()
    assert all(r["value"] == r["ref"].upper() for r in rows)
    assert summary.cost == pytest.approx(summary.usage.cost(PRICES, batch=True))
    assert not (core.STATE_DIR / "shout.json").exists()  # cleared once results are saved


def test_errored_requests_are_not_stored_so_the_next_run_retries_them(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    client.error_ids = {"shout-a1-00000"}  # the first request (apple, pear, fig) errors
    summary = run(client, tmp_path / "out.jsonl", WORDS, batch=True)
    assert (summary.ok, summary.errored) == (2, 3)
    client.error_ids = set()
    assert run(client, tmp_path / "out.jsonl", WORDS, batch=True).ok == 3


def test_an_interrupted_batch_is_collected_not_resubmitted(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    task, settings = Shout(), core.CallSettings(model="model-x", thinking_off=True)
    payloads = [{"word": w} for w in WORDS[:3]]
    keys = [core.cache_key(task, settings, p) for p in payloads]
    batch = client.messages.batches.create(
        requests=[
            {"custom_id": "shout-a1-00000", "params": core.request_params(task, settings, payloads)}
        ]
    )
    core.STATE_DIR.mkdir(parents=True)
    (core.STATE_DIR / "shout.json").write_text(
        json.dumps(
            {
                "batch_id": batch.id,
                "settings": settings.__dict__,
                "requests": {"shout-a1-00000": keys},
            }
        )
    )

    summary = run(client, tmp_path / "out.jsonl", WORDS, batch=True)
    assert client.batches_created == 2  # the earlier one, plus one for the two words left
    assert summary.ok == 2 and summary.cached == 3


def test_cache_key_covers_model_prompt_version_and_input() -> None:
    task = Shout()
    base = core.cache_key(task, core.CallSettings("model-x", True), {"word": "a"})
    assert base != core.cache_key(task, core.CallSettings("model-y", True), {"word": "a"})
    assert base != core.cache_key(task, core.CallSettings("model-x", False), {"word": "a"})
    assert base != core.cache_key(task, core.CallSettings("model-x", True), {"word": "b"})
    task.prompt_version = "shout-v2"
    assert base != core.cache_key(task, core.CallSettings("model-x", True), {"word": "a"})


def test_request_asks_for_json_matching_the_schema() -> None:
    params = core.request_params(Shout(), core.CallSettings("model-x", True), [{"word": "a"}])
    schema = params["output_config"]["format"]["schema"]
    assert schema["properties"]["items"]["items"]["required"] == ["id", "value"]
    assert params["thinking"] == {"type": "disabled"}
    assert "thinking" not in core.request_params(
        Shout(), core.CallSettings("model-x", False), [{"word": "a"}]
    )


def test_refusals_and_bad_json_make_every_item_invalid() -> None:
    from pipeline.tests.fake_anthropic import Block, Message

    task, payloads = Shout(), [{"word": "a"}, {"word": "b"}]
    assert core.parse_response(task, payloads, Message([Block("{}")], "refusal")) == [None, None]
    assert core.parse_response(task, payloads, Message([Block("not json")])) == [None, None]
    partial = json.dumps({"items": [{"id": 2, "value": "B"}, {"id": 9, "value": "Z"}]})
    assert core.parse_response(task, payloads, Message([Block(partial)])) == [None, "B"]


def test_identical_inputs_share_one_call_but_each_ref_gets_a_row(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    summary = run(
        client, tmp_path / "out.jsonl", ["cola", "cola", "tea"], refs=["001", "002", "003"]
    )
    assert summary.uncached == 2 and summary.ok == 2
    sent = client.calls[0]["messages"][0]["content"]
    assert sent.count("cola") == 1
    rows = core.OutputStore(tmp_path / "out.jsonl").load()
    assert {(r["ref"], r["value"]) for r in rows} == {
        ("001", "COLA"),
        ("002", "COLA"),
        ("003", "TEA"),
    }


def test_prune_keeps_only_current_items(tmp_path: Path) -> None:
    client = FakeAnthropic(shouter())
    run(client, tmp_path / "out.jsonl", WORDS)
    run(client, tmp_path / "out.jsonl", ["apple", "fig"], prune=True)
    assert {r["ref"] for r in core.OutputStore(tmp_path / "out.jsonl").load()} == {"apple", "fig"}
    run(client, tmp_path / "out.jsonl", ["apple", "fig", "kiwi"])  # without prune: kept, added
    refs = [r["ref"] for r in core.OutputStore(tmp_path / "out.jsonl").load()]
    assert refs == ["apple", "fig", "kiwi"]


# Real runs: (characters the estimator counts, requests, input tokens billed). The estimate
# must stay above each; with 3 characters per token it was a third under on the fill.
MEASURED_RUNS = {
    "categories fill": (106_338_363, 12_093, 51_669_473),
    "additive explainers": (106_623, 54, 53_714),
    "ingredient explainers": (71_721, 51, 38_763),
}


@pytest.mark.parametrize("name", list(MEASURED_RUNS))
def test_the_input_estimate_is_above_every_measured_run(name: str) -> None:
    chars, requests, billed = MEASURED_RUNS[name]
    estimated = chars / core.CHARS_PER_TOKEN + core.REQUEST_OVERHEAD_TOKENS * requests
    assert estimated >= billed


def test_category_output_estimate_is_above_the_measured_rate() -> None:
    from pipeline.enrich.categories import CategoryTask

    assert CategoryTask.output_tokens_per_item >= 10_370_267 / 604_507  # 17.2 per product
