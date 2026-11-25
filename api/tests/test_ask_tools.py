"""The ask agent's tools on the test Postgres (read-only role) and the test Neo4j."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import pytest
from psycopg.rows import dict_row

from api.app.ask import tools as tools_module
from api.app.ask.tools import (
    ROW_LIMIT,
    Citations,
    ToolError,
    Tools,
    check_sql,
    iter_cites,
    trim,
)
from api.app.db import DictConnection
from api.app.graph import Graph
from pipeline.tests.fake_voyage import FakeVoyageServer

Connect = Callable[[], AbstractContextManager[DictConnection]]


@pytest.fixture(scope="module")
def connect(readonly_url: str) -> Connect:
    @contextmanager
    def lend() -> Iterator[DictConnection]:
        with DictConnection.connect(
            readonly_url, autocommit=True, prepare_threshold=None, row_factory=dict_row
        ) as conn:
            yield conn

    return lend


def _tools(connect: Connect, graph: Graph | None = None, voyage=None) -> Tools:
    return Tools(connect, graph or Graph(driver=None), voyage or FakeVoyageServer().client())


def _run(tools: Tools, name: str, **arguments: Any) -> tuple[dict[str, Any], Any]:
    result = tools.run(name, arguments)
    return json.loads(result.content), result


# --- Pure checks ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["select 1", "  SELECT 1;  ", "with x as (select 1) select * from x", "-- note\nselect 1"],
)
def test_check_sql_accepts_one_read(text: str) -> None:
    assert check_sql(text).lower().lstrip("- note\n").startswith(("select", "with"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "empty"),
        ("select 1; select 2", "one statement"),
        ("delete from products", "Only SELECT"),
        ("/* select */ update products set name = 'x'", "Only SELECT"),
        ("explain select 1", "Only SELECT"),
    ],
)
def test_check_sql_refuses_the_rest(text: str, message: str) -> None:
    with pytest.raises(ToolError, match=message):
        check_sql(text)


def test_trim_keeps_results_small() -> None:
    assert trim("x" * 400).endswith("…") and len(trim("x" * 400)) == 301
    assert trim(list(range(20)))[-1] == "… 8 more"
    assert trim(1.23456) == 1.235
    assert trim({"a": ["y" * 400]})["a"][0].endswith("…")


def test_citations_are_stable_and_per_kind() -> None:
    cites = Citations()
    assert cites.add("row", "1", "A", "/products/1") == "R1"
    assert cites.add("row", "2", "B", "/products/2") == "R2"
    assert cites.add("row", "1", "A again", None) == "R1"
    assert cites.add("node", "Product:1", "A", "/graph?code=1") == "N1"
    assert cites.add("explainer", "en:e330", "Citric acid", None) == "E1"
    cite = cites.get("R2")
    assert cite and cite.ref == "2" and cite.url == "/products/2"
    assert cites.get("R9") is None and len(cites) == 4


def test_iter_cites_reads_single_and_grouped_ids_in_order() -> None:
    text = "Two cereals [R2] and [R1, N3]; sugar [E1]. Again [R2]. Not [X1] or [R]."
    assert list(iter_cites(text)) == ["R2", "R1", "N3", "E1"]


# --- query_sql -----------------------------------------------------------------------------


def test_product_rows_are_cited_with_product_links(connect: Connect) -> None:
    tools = _tools(connect)
    data, result = _run(
        tools, "query_sql", summary="Top products",
        sql="select code, name, brand, nutriscore_grade from products order by rank_pos limit 3",
    )  # fmt: skip
    assert not result.is_error and result.row_count == 3 and result.summary == "Top products"
    assert [row["cite"] for row in data["rows"]] == ["R1", "R2", "R3"]
    cite = tools.citations.get("R1")
    assert cite and cite.url == f"/products/{data['rows'][0]['code']}"


def test_an_aggregate_gets_one_citation(connect: Connect) -> None:
    tools = _tools(connect)
    data, _ = _run(
        tools, "query_sql",
        sql="select nutriscore_grade, count(*) as n from products group by 1 order by 1",
    )  # fmt: skip
    assert {row["cite"] for row in data["rows"]} == {"R1"}
    cite = tools.citations.get("R1")
    assert cite and cite.url is None and cite.ref == "query:1"


def test_results_stop_at_the_row_limit(connect: Connect) -> None:
    data, result = _run(_tools(connect), "query_sql", sql="select code from products")
    assert result.row_count == ROW_LIMIT and "first 50" in data["note"]


def test_a_trailing_comment_cannot_escape_the_wrapper(connect: Connect) -> None:
    _data, result = _run(_tools(connect), "query_sql", sql="select code from products -- all")
    assert result.row_count == ROW_LIMIT and not result.is_error


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("select * from meta", "Permission denied"),
        ("select * from serving.stats", "Permission denied"),
        ("select * from app.ask_runs", "Permission denied"),
        ("with d as (delete from products returning code) select * from d", "SQL error"),
        ("select nope from products", 'column "nope" does not exist'),
        ("insert into products (code) values ('1')", "Only SELECT"),
    ],
)
def test_refused_queries_come_back_as_messages(connect: Connect, sql: str, message: str) -> None:
    data, result = _run(_tools(connect), "query_sql", sql=sql)
    assert result.is_error and message in data["error"]


def test_a_slow_query_is_stopped(connect: Connect) -> None:
    data, result = _run(_tools(connect), "query_sql", sql="select pg_sleep(5)")
    assert result.is_error and "ran past 3s" in data["error"]
    assert result.duration_ms < 4500


def test_swaps_runs_the_product_page_rule(connect: Connect) -> None:
    with connect() as conn:
        row = conn.execute(
            "select code from serving.products where nutriscore_grade in ('d', 'e') "
            "and category_id is not null and category_id <> 'other' order by rank_pos limit 1"
        ).fetchone()
    assert row
    tools = _tools(connect)
    data, result = _run(tools, "query_graph", template="swaps", code=row["code"])
    assert not result.is_error and data["code"] == row["code"]
    for swap in data["swaps"]:
        cite = tools.citations.get(swap["cite"])
        assert cite and cite.kind == "row" and cite.url == f"/products/{swap['code']}"
    data, result = _run(tools, "query_graph", template="swaps", code="999")
    assert result.is_error and "No product" in data["error"]


# --- search_explainers ---------------------------------------------------------------------


def test_explainer_search_finds_the_closest_text(connect: Connect) -> None:
    server = FakeVoyageServer()
    tools = _tools(connect, voyage=server.client())
    with connect() as conn:
        target = conn.execute(
            "select name, text from serving.explainers where id = 'en:e330'"
        ).fetchone()
    assert target
    data, result = _run(tools, "search_explainers", query=f"{target['name']}: {target['text']}")
    assert not result.is_error and result.embedding_tokens > 0
    assert data["results"][0]["id"] == "en:e330" and data["results"][0]["cite"] == "E1"
    assert server.requests[0]["input_type"] == "query"
    assert "AI-written" in data["note"]


def test_an_e_number_in_the_question_is_looked_up_exactly_first(connect: Connect) -> None:
    tools = _tools(connect, voyage=FakeVoyageServer().client())
    data, result = _run(tools, "search_explainers", query="What does E330 do in food?")
    assert not result.is_error
    first = data["results"][0]
    assert first["id"] == "en:e330" and first["match"] == "E-number"
    assert first["cite"] == "E1" and "distance" not in first
    ids = [r["id"] for r in data["results"]]
    assert len(ids) == len(set(ids)) <= 5  # the vector results fill the rest, no repeats


def test_an_e_number_is_found_even_without_voyage(connect: Connect) -> None:
    tools = _tools(connect, voyage=FakeVoyageServer().client(key=None))
    data, result = _run(tools, "search_explainers", query="what is e330")
    assert not result.is_error and result.embedding_tokens == 0
    assert [r["id"] for r in data["results"]] == ["en:e330"]


def test_explainer_search_without_voyage_points_to_sql(connect: Connect) -> None:
    tools = _tools(connect, voyage=FakeVoyageServer().client(key=None))
    data, result = _run(tools, "search_explainers", query="what is lecithin")
    assert result.is_error and "query_sql" in data["error"]


def test_e_numbers_are_read_out_of_a_question() -> None:
    assert tools_module.e_number_ids("What is E412?") == ["en:e412"]
    assert tools_module.e_number_ids("is e330 or E322i in it, and E330 again") == [
        "en:e330",
        "en:e322i",
    ]
    assert tools_module.e_number_ids("E-322 and E339(iii) and E160b") == [
        "en:e322",
        "en:e339iii",
        "en:e160b",
    ]
    # A dose is not an E-number, nor is a code inside a word.
    assert tools_module.e_number_ids("vitamin E 400 IU") == []
    assert tools_module.e_number_ids("TE412 or E41") == []


def test_an_e_number_picks_its_own_explainer_else_a_narrower_one() -> None:
    pick = tools_module.pick_exact
    assert pick(["en:e322"], ["en:e322i", "en:e3220"]) == ["en:e322i"]  # not E3220
    assert pick(["en:e160b"], ["en:e160", "en:e160b", "en:e160bi"]) == ["en:e160b"]
    assert pick(["en:e999"], ["en:e330"]) == []
    assert pick(["en:e330", "en:e330"], ["en:e330"]) == ["en:e330"]


# --- query_graph ---------------------------------------------------------------------------


def test_graph_templates_run_on_neo4j(connect: Connect, fixture_graph: Any) -> None:
    graph = Graph(driver=fixture_graph)
    tools = _tools(connect, graph)

    data, result = _run(tools, "query_graph", template="products_sharing_additive",
                        additive="e330")  # fmt: skip
    assert not result.is_error, data
    assert data["additive"]["id"] == "en:e330" and data["products_in_graph"] >= len(
        data["products"]
    )
    assert all(tools.citations.get(p["cite"]).url.startswith("/graph?code=")  # type: ignore[union-attr]
               for p in data["products"])  # fmt: skip

    records, _, _ = fixture_graph.execute_query(
        "MATCH (p:Product)-[:HAS_INGREDIENT]->() WITH p, count(*) AS n "
        "RETURN p.code AS code, p.category AS category ORDER BY n DESC, p.rank LIMIT 1"
    )
    code, category = records[0]["code"], records[0]["category"]
    data, result = _run(tools, "query_graph", template="shared_ingredients", code=code)
    assert not result.is_error and data["product"]["code"] == code
    shared = [p["shared_count"] for p in data["similar_in_category"]]
    assert shared == sorted(shared, reverse=True)

    data, result = _run(tools, "query_graph", template="category_neighbours", category=category)
    assert not result.is_error and data["category"]["id"] == category
    assert data["products_in_graph"] > 0 and data["parent"]

    data, result = _run(tools, "query_graph", template="shared_ingredients", code="999")
    assert result.is_error and "does not hold" in data["error"]
    data, result = _run(tools, "query_graph", template="products_sharing_additive",
                        additive="E99999")  # fmt: skip
    assert result.is_error and "No additive" in data["error"]


def test_graph_problems_come_back_as_messages(connect: Connect) -> None:
    tools = _tools(connect)  # no graph configured
    data, result = _run(tools, "query_graph", template="category_neighbours", category="x")
    assert result.is_error and "query_sql instead" in data["error"]
    data, result = _run(tools, "query_graph", template="anything")
    assert result.is_error and "Unknown template" in data["error"]
    data, result = _run(tools, "query_graph", template="shared_ingredients")
    assert result.is_error and "needs `code`" in data["error"]
    data, result = _run(tools, "nope")
    assert result.is_error and "no tool called" in data["error"]
