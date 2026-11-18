"""POST /label and GET /ready with a scripted model: images, normalising, matching, limits,
the run log, and that no image ever reaches the trace."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.config import Settings
from api.app.db import DictConnection
from api.app.graph import Graph
from api.app.label import images
from api.app.label.categories import LEAF_CATEGORIES
from api.app.label.normalise import NO_SERVING, nutrition_per_100g
from api.app.label.reading import LabelReading, PrintedNutrition, request_params
from api.app.label.service import OVER_CAP, READ_FAILED, names_agree
from api.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


def nutrition(**values: float | None) -> PrintedNutrition:
    keys = PrintedNutrition.model_fields
    return PrintedNutrition(**{k: values.get(k) for k in keys})


def reading(**over: Any) -> LabelReading:
    base: dict[str, Any] = {
        "is_food_label": True,
        "name": None,
        "brand": None,
        "barcode": None,
        "basis": "per_serving",
        "serving_size_g": 30.0,
        "nutrition": nutrition(energy_kcal=120, fat_g=3, sodium_mg=200, sugars_g=6, protein_g=2),
        "ingredients": ["whole grain oats", "sugar", "salt"],
        "additives": [],
        "category_id": "breakfast-cereals",
    }
    return LabelReading(**(base | over))


# --- Pure pieces ---------------------------------------------------------------------------


def test_image_types_come_from_the_bytes_not_the_name() -> None:
    assert images.sniff(JPEG) == "image/jpeg"
    assert images.sniff(PNG) == "image/png"
    assert images.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert images.sniff(b"GIF89a") is None
    assert [i.media_type for i in images.check([JPEG, PNG])] == ["image/jpeg", "image/png"]


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "Add a photo"),
        ([JPEG, JPEG, JPEG], "At most 2"),
        ([b"%PDF-1.7"], "JPEG, PNG or WebP"),
        ([b"\xff\xd8\xff" + b"0" * images.MAX_BYTES], "over 5 MB"),
    ],
)
def test_uploads_that_cannot_be_read_say_why(files: list[bytes], message: str) -> None:
    with pytest.raises(images.ImageError, match=message):
        images.check(files)


def test_per_serving_becomes_per_100g_with_sodium_as_salt() -> None:
    values, note = nutrition_per_100g(reading())
    assert values["energy_kcal_100g"] == 400.0
    assert values["fat_100g"] == 10.0
    assert values["salt_100g"] == pytest.approx(1.67, abs=0.01)  # 200 mg sodium x 2.5, /30 g
    assert values["sugars_100g"] == 20.0
    assert values["fiber_100g"] is None
    assert note == "Converted from per serving (30 g or ml) to per 100 g or ml."


def test_per_100g_is_taken_as_printed_and_kj_becomes_kcal() -> None:
    label = reading(
        basis="per_100g", serving_size_g=None, nutrition=nutrition(energy_kj=1674, salt_g=0.8)
    )
    values, note = nutrition_per_100g(label)
    assert values["energy_kcal_100g"] == pytest.approx(400.1, abs=0.1)
    assert values["salt_100g"] == 0.8
    assert note is None


def test_without_a_serving_size_nothing_is_guessed() -> None:
    values, note = nutrition_per_100g(reading(serving_size_g=None))
    assert set(values.values()) == {None}
    assert note == NO_SERVING


def test_values_that_cannot_be_true_are_dropped() -> None:
    # 60 g of fat in a 30 g serving is 200 g per 100 g; 400 kcal in 30 g is over 900 per 100 g.
    values, _ = nutrition_per_100g(reading(nutrition=nutrition(fat_g=60, energy_kcal=400)))
    assert values["fat_100g"] is None
    assert values["energy_kcal_100g"] is None


def test_names_agree_needs_most_of_the_words_and_the_brand() -> None:
    label = reading(name="Honey Nut Cheerios", brand="General Mills")
    assert names_agree(label, {"name": "Honey Nut Cheerios", "brand": "General Mills"})
    assert not names_agree(label, {"name": "Honey Nut Cheerios", "brand": "Kellogg's"})
    assert not names_agree(label, {"name": "Cheerios", "brand": "General Mills"})
    assert not names_agree(reading(name=None), {"name": "Cheerios", "brand": None})


def test_categories_are_the_seed_leaves() -> None:
    with open(ROOT / "pipeline/dbt/seeds/dim_categories.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    parents = {r["parent_id"] for r in rows if r["parent_id"]}
    leaves = {r["category_id"]: r["name"] for r in rows if r["category_id"] not in parents}
    assert leaves == LEAF_CATEGORIES


def test_the_request_sends_images_once_and_caches_the_prompt() -> None:
    params = request_params("claude-haiku-5-5", images.check([JPEG, PNG]))
    content = params["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    assert content[1]["source"]["media_type"] == "image/png"
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert params["thinking"] == {"type": "disabled"}
    # Sonnet 5.5 turns thinking off differently; the setting lives in config with the models.
    assert request_params("claude-sonnet-5-5", [])["thinking"] == {"type": "between_tools"}


# --- The endpoint --------------------------------------------------------------------------


@dataclass
class Usage:
    input_tokens: int = 1800
    output_tokens: int = 300
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Parsed:
    parsed_output: LabelReading | None
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)


class FakeClient:
    """messages.parse returns the scripted readings in order."""

    def __init__(self, *outputs: LabelReading | None):
        self.outputs = list(outputs)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def parse(self, **params: Any) -> Parsed:
        self.calls.append(params)
        output = self.outputs.pop(0)
        return Parsed(output, "refusal" if output is None else "end_turn")


class RecordingTracer:
    """Records everything handed to Langfuse, to prove no image goes there."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []

    def trace(self, name: str, **fields: Any) -> RecordingTracer:
        self.seen.append(fields)
        return self

    def child(self, name: str, as_type: str, **fields: Any) -> RecordingTracer:
        self.seen.append(fields)
        return self

    def update(self, **fields: Any) -> None:
        self.seen.append(fields)

    def end(self, **fields: Any) -> None:
        self.seen.append(fields)

    def flush(self) -> None:
        pass


def _app(serving_url: str, client: FakeClient, tracer: RecordingTracer | None = None, **over: Any):
    settings = Settings(_env_file=None, database_url=serving_url, **over)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    app.state.graph = Graph(driver=None)
    app.state.label_client = client
    app.state.tracer = tracer or RecordingTracer()
    return app


@pytest.fixture
def ip(request: pytest.FixtureRequest) -> str:
    return f"198.51.100.{abs(hash(request.node.name)) % 250 + 1}"


@pytest.fixture
def cleanup(serving_url: str) -> Iterator[None]:
    yield
    with psycopg.connect(serving_url, autocommit=True) as pg:
        pg.execute("delete from app.ask_runs where client_hash <> 'test'")


@pytest.fixture(scope="module")
def known(serving_url: str) -> dict[str, Any]:
    """A real product from the fixture, with a brand and an additive that has an E-number."""
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        row = pg.execute(
            """
            select p.code, p.name, p.brand, a.additive_id, a.e_number
            from serving.products p
            join serving.additives a on a.additive_id = p.additive_ids[1]
            where p.brand is not null and a.e_number is not null
            order by p.rank_pos limit 1
            """
        ).fetchone()
    assert row, "the fixture has no branded product with an additive"
    return row


def _post(client: TestClient, ip: str, *files: bytes) -> Any:
    return client.post(
        "/label",
        files=[("images", (f"label{i}.jpg", data, "image/jpeg")) for i, data in enumerate(files)],
        headers={"X-Forwarded-For": ip},
    )


def _runs(serving_url: str) -> list[dict[str, Any]]:
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        return pg.execute(
            "select kind, outcome, cost_usd, input_tokens from app.ask_runs "
            "where client_hash <> 'test' order by id"
        ).fetchall()


def test_a_label_is_read_explained_and_matched_by_name(
    serving_url: str, known: dict[str, Any], ip: str, cleanup: None
) -> None:
    label = reading(
        name=known["name"], brand=known["brand"], additives=[known["e_number"]], barcode=None
    )
    tracer = RecordingTracer()
    fake = FakeClient(label)
    with TestClient(_app(serving_url, fake, tracer)) as client:
        response = _post(client, ip, JPEG, PNG)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_food_label"] and body["source"]["name"] == "Open Food Facts"
    assert body["match"]["how"] == "name"
    assert body["match"]["product"]["code"] == known["code"]
    assert body["label"]["conversion_note"].startswith("Converted from per serving")
    assert body["label"]["nutrition"]["energy_kcal_100g"] == 400.0
    found = {a["additive_id"]: a for a in body["label"]["additives"]}
    assert known["additive_id"] in found and "flagged" in found[known["additive_id"]]
    assert [i["rank"] for i in body["label"]["ingredients"]] == [1, 2, 3]
    assert body["suggestions_kind"] in {"swaps", None}

    (run,) = _runs(serving_url)
    assert run["kind"] == "label" and run["outcome"] == "answer"
    assert float(run["cost_usd"]) > 0 and run["input_tokens"] == 1800

    # The photos went to the model, and never to the trace.
    assert len(fake.calls[0]["messages"][0]["content"]) == 3
    traced = json.dumps(tracer.seen, default=str)
    assert "[2 images]" in traced and "base64" not in traced and "/9j/" not in traced


def test_a_barcode_in_the_photo_matches_first(
    serving_url: str, known: dict[str, Any], ip: str, cleanup: None
) -> None:
    label = reading(name="Something else entirely", barcode=known["code"])
    with TestClient(_app(serving_url, FakeClient(label))) as client:
        body = _post(client, ip, JPEG).json()
    assert body["match"]["how"] == "barcode"
    assert body["match"]["product"]["code"] == known["code"]


def test_an_unknown_product_gets_well_graded_products_like_it(
    serving_url: str, ip: str, cleanup: None
) -> None:
    label = reading(name="Zzqx Imported Puffs", brand="Nobrand", category_id="salty-snacks")
    with TestClient(_app(serving_url, FakeClient(label))) as client:
        body = _post(client, ip, JPEG).json()
    assert body["match"] is None
    assert body["suggestions_kind"] in {"category", None}
    for swap in body["suggestions"]:
        assert swap["product"]["nutriscore_grade"] in {"a", "b"}
        assert swap["reason"].startswith("Nutri-Score")


def test_a_photo_that_is_not_a_label_says_so(serving_url: str, ip: str, cleanup: None) -> None:
    not_food = reading(is_food_label=False, ingredients=[], category_id="other")
    with TestClient(_app(serving_url, FakeClient(not_food))) as client:
        body = _post(client, ip, JPEG).json()
    assert body["is_food_label"] is False and body["label"] is None
    assert _runs(serving_url)[0]["outcome"] == "not_label"


def test_bad_uploads_are_422_and_never_reach_the_model(
    serving_url: str, ip: str, cleanup: None
) -> None:
    fake = FakeClient()
    with TestClient(_app(serving_url, fake)) as client:
        assert _post(client, ip, b"%PDF-1.7 not a photo").status_code == 422
        assert _post(client, ip, JPEG, JPEG, JPEG).status_code == 422
        assert client.post("/label", json={"images": []}).status_code == 422
    assert fake.calls == []


def test_a_failed_read_is_422_and_still_logged(serving_url: str, ip: str, cleanup: None) -> None:
    with TestClient(_app(serving_url, FakeClient(None))) as client:
        response = _post(client, ip, JPEG)
    assert response.status_code == 422 and response.json()["detail"] == READ_FAILED
    (run,) = _runs(serving_url)
    assert run["outcome"] == "failed" and float(run["cost_usd"]) > 0


def test_label_reads_have_their_own_hourly_limit(serving_url: str, ip: str, cleanup: None) -> None:
    fake = FakeClient(reading(), reading())
    app = _app(serving_url, fake, label_rate_limit_per_hour=1)
    with TestClient(app) as client:
        assert _post(client, ip, JPEG).status_code == 200
        limited = _post(client, ip, JPEG)
        ready = client.get("/ready", headers={"X-Forwarded-For": ip}).json()
    assert limited.status_code == 429 and "1 labels this hour" in limited.json()["detail"]
    assert 3000 <= int(limited.headers["Retry-After"]) <= 3601
    assert len(fake.calls) == 1
    assert ready["label_reads_left"] == 0
    assert ready["questions_left"] == 10  # questions are counted apart


def test_over_the_daily_cap_no_model_is_called(serving_url: str, ip: str, cleanup: None) -> None:
    fake = FakeClient(reading())
    app = _app(serving_url, fake, ask_daily_spend_cap_usd=0.0)
    with TestClient(app) as client:
        response = _post(client, ip, JPEG)
    assert response.status_code == 503 and response.json()["detail"] == OVER_CAP
    assert fake.calls == []
    assert _runs(serving_url)[0]["outcome"] == "over_cap"


def test_ready_reports_what_a_demo_has_left(serving_url: str, ip: str, cleanup: None) -> None:
    with TestClient(_app(serving_url, FakeClient())) as client:
        body = client.get("/ready", headers={"X-Forwarded-For": ip}).json()
    assert body["label_configured"] is True
    assert body["ask_configured"] is False  # no read-only database in these settings
    assert body["label_reads_left"] == 10 and body["questions_left"] == 10
    assert body["daily_cap_usd"] == 0.5 and body["spent_today_usd"] >= 0
    assert body["source"]["name"] == "Open Food Facts"
