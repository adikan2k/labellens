"""The recorded replays match the page's examples and the /ask contract."""

from __future__ import annotations

import re

from api.app.ask.service import REPLAY_DIR, load_replays
from api.app.schemas import AskAnswer, AskStep, Citation
from scripts import record_replays


def test_examples_are_read_from_the_web_copy() -> None:
    questions = record_replays.examples()
    assert len(questions) == 3
    assert all(q and '"' not in q for q in questions)
    assert record_replays.slug(questions[0]) == "breakfast-cereals-under-5-g"


def test_there_is_one_replay_per_example_question() -> None:
    replays = load_replays(REPLAY_DIR)
    assert sorted(r.question for r in replays) == sorted(record_replays.examples())


def test_replays_fit_the_contract_and_cite_what_they_number() -> None:
    for replay in load_replays(REPLAY_DIR):
        steps = [AskStep.model_validate(s) for s in replay.steps]
        assert 1 <= len(steps) <= 6, replay.question
        # The service adds `replay` and `source` when it serves one.
        assert set(replay.answer) == set(AskAnswer.model_fields) - {"replay", "source"}
        citations = [Citation.model_validate(c) for c in replay.answer["citations"]]
        assert [c.n for c in citations] == list(range(1, len(citations) + 1))
        assert not replay.answer["refused"] and citations, replay.question
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", replay.answer["text"])}
        assert cited and max(cited) <= len(citations), replay.question


def test_a_replay_keeps_the_run_and_its_provenance() -> None:
    run = {"question": "q", "steps": [{"index": 1}], "text": "t [1]", "citations": [{"n": 1}],
           "refused": False, "model": "m", "prompt_version": "ask-v1", "cost_usd": 0.001,
           "duration_ms": 900, "tools": ["query_sql"]}  # fmt: skip
    out = record_replays.replay(run)
    assert out["answer"] == {"text": "t [1]", "citations": [{"n": 1}], "refused": False}
    assert out["recorded"]["prompt_version"] == "ask-v1" and "tools" not in out
