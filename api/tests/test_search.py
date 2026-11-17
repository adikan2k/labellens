"""GET /search against the fixture loaded into a throwaway Postgres database."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app import search
from api.app.config import Settings
from api.app.main import WAKING_UP, create_app


@pytest.fixture(scope="module")
def client(serving_url: str) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, database_url=serving_url)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def products(serving_url: str) -> list[dict[str, Any]]:
    with psycopg.connect(serving_url, autocommit=True) as pg:
        cur = pg.cursor(row_factory=dict_row)
        return cur.execute(
            "select code, name, brand, rank_pos from serving.products order by rank_pos"
        ).fetchall()


def _get(client: TestClient, q: str, **params: Any) -> dict[str, Any]:
    response = client.get("/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _a_word(products: list[dict[str, Any]], min_len: int = 5) -> tuple[str, dict[str, Any]]:
    for p in products:
        for word in search.words(p["name"]):
            if len(word) >= min_len and word.isalpha() and word.isascii():
                return word, p
    raise AssertionError("fixture has no usable product word")


def test_name_word_finds_the_product_in_rank_order(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    word, product = _a_word(products)
    body = _get(client, word, limit=50)
    codes = [r["code"] for r in body["results"]]
    assert product["code"] in codes
    rank = {p["code"]: p["rank_pos"] for p in products}
    assert [rank[c] for c in codes] == sorted(rank[c] for c in codes)
    assert body["query"] == word
    assert body["source"]["snapshot_date"] == "2026-11-17"


def test_partial_last_word_matches_while_typing(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    word, product = _a_word(products, min_len=6)
    codes = [r["code"] for r in _get(client, word[:4], limit=50)["results"]]
    assert product["code"] in codes


def test_brand_search_reports_brand_match(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    for p in products:
        brand_words = [w for w in search.words(p["brand"] or "") if len(w) >= 4 and w.isalpha()]
        if brand_words and brand_words[0] not in search.words(p["name"]):
            body = _get(client, brand_words[0], limit=50)
            hit = next(r for r in body["results"] if r["code"] == p["code"])
            assert hit["match"] == "brand"
            return
    pytest.skip("no product whose brand word is absent from its name")


def test_barcode_full_and_prefix(client: TestClient, products: list[dict[str, Any]]) -> None:
    code = next(p["code"] for p in products if len(p["code"]) == 13)
    full = _get(client, code)["results"]
    assert full[0]["code"] == code
    assert full[0]["match"] == "barcode"
    assert code in [r["code"] for r in _get(client, code[:8], limit=50)["results"]]


def test_twelve_digit_upc_finds_the_thirteen_digit_ean(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    code = next((p["code"] for p in products if len(p["code"]) == 13 and p["code"][0] == "0"), None)
    if code is None:
        pytest.skip("fixture has no EAN-13 with a leading zero")
    assert _get(client, code[1:])["results"][0]["code"] == code


def test_result_shape_follows_the_contract(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    word, _ = _a_word(products)
    result = _get(client, word)["results"][0]
    assert set(result) == {
        "code", "name", "brand", "category_main", "nutriscore_grade", "nova_group",
        "image_url", "match",
    }  # fmt: skip
    if result["image_url"]:
        assert result["image_url"].startswith(search.IMAGE_BASE)
        assert result["image_url"].endswith(".400.jpg")


@pytest.mark.parametrize(
    "q",
    [
        "zzqxqzz",
        "the",
        "'; drop table serving.products; --",
        "a & | ! :* <->",
        "%_%",
        "  ",
        "ñandú",
    ],
)
def test_odd_queries_are_safe_and_answer_200(client: TestClient, q: str) -> None:
    response = client.get("/search", params={"q": q})
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["results"], list)


def test_products_table_survives_injection_attempt(client: TestClient, serving_url: str) -> None:
    client.get("/search", params={"q": "x'); drop table serving.products; --"})
    with psycopg.connect(serving_url, autocommit=True) as pg:
        row = pg.execute("select count(*) from serving.products").fetchone()
    assert row and row[0] > 0


def test_limit_is_respected_and_validated(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    word, _ = _a_word(products)
    assert len(_get(client, word, limit=1)["results"]) <= 1
    for bad in (0, 51):
        response = client.get("/search", params={"q": word, "limit": bad})
        assert response.status_code == 422
        body = response.json()
        assert body["detail"].startswith("Invalid request.")
        assert body["source"]["name"] == "Open Food Facts"
    assert client.get("/search").status_code == 422


def test_search_is_cacheable_for_a_minute(
    client: TestClient, products: list[dict[str, Any]]
) -> None:
    word, _ = _a_word(products)
    response = client.get("/search", params={"q": word})
    assert response.headers["cache-control"] == "public, max-age=60"


def test_unreachable_database_says_waking_up() -> None:
    unreachable = "postgresql://nobody@127.0.0.1:1/none"
    settings = Settings(_env_file=None, database_url=unreachable, db_pool_timeout=1)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as client:
        response = client.get("/search", params={"q": "milk"})
    assert response.status_code == 503
    assert response.json()["detail"] == WAKING_UP
    assert response.json()["source"]["snapshot_date"] is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("honey nut chee", "honey & nut & chee:*"),
        ("Coca-Cola", "coca & cola:*"),
        ("  ", None),
        ("a & b | c", "a & b & c:*"),
        ("crème brûlée", "crème & brûlée:*"),
    ],
)
def test_tsquery_is_built_from_words_only(text: str, expected: str | None) -> None:
    assert search.to_tsquery(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0016000275263", "0016000275263"), ("016000-275263", "016000275263"), ("12", None),
     ("coke 2l", None)],
)  # fmt: skip
def test_barcode_detection(text: str, expected: str | None) -> None:
    assert search.barcode_digits(text) == expected
