"""Session fixtures shared by pipeline and API tests.

- dbt_fixture: one dbt build of the committed fixture per test session.
- fixture_embeddings: the fixture's explainers embedded by the fake Voyage (no network).
- readonly_role: the ask agent's read-only role in the test Postgres (roles are cluster-wide;
  each session gives it a new password). readonly_url: that role on the serving_url database.
- serving_url: a throwaway Postgres database with the fixture loaded into the serving schema.
  Needs the test Postgres (docker compose up -d postgres). Locally the database tests are
  skipped with that hint when it is not running; in CI (CI=true) they fail instead.
- neo4j_driver: a driver for the test Neo4j (docker compose up -d neo4j-test), same
  skip-or-fail rule. Tests replace its contents; the development Neo4j is a separate server.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pipeline.tests.support import FIXTURE_VARS, Build, run_dbt, test_database_url

TEST_NEO4J = (
    os.environ.get("TEST_NEO4J_URI", "bolt://localhost:57688"),
    os.environ.get("TEST_NEO4J_USER", "neo4j"),
    os.environ.get("TEST_NEO4J_PASSWORD", "labellens-local"),
)


@pytest.fixture(scope="session")
def dbt_fixture(tmp_path_factory: pytest.TempPathFactory) -> Build:
    tmp = tmp_path_factory.mktemp("dbt")
    return Build(run_dbt("build", tmp, FIXTURE_VARS), tmp / "fixture.duckdb", tmp)


@pytest.fixture(scope="session")
def fixture_embeddings(dbt_fixture: Build) -> Path:
    from pipeline.enrich import embeddings
    from pipeline.tests.fake_voyage import FakeVoyageServer

    assert dbt_fixture.run.returncode == 0, dbt_fixture.run.output[-3000:]
    path = dbt_fixture.tmp / "explainer_embeddings.parquet"
    embeddings.run(
        embeddings.load_texts(dbt_fixture.db),
        voyage_factory=FakeVoyageServer().client,
        model="voyage-4-lite",
        price_per_mtok=0.02,
        store=path,
        limit=10_000,
        yes=True,
        log=lambda *_: None,
    )
    return path


@pytest.fixture(scope="session")
def pg_admin_url() -> str:
    url = test_database_url()
    try:
        with psycopg.connect(url, connect_timeout=3):
            pass
    except psycopg.OperationalError as error:
        message = f"Test Postgres not reachable at {url}: run `docker compose up -d postgres`."
        if os.environ.get("CI"):
            pytest.fail(f"{message} ({error})")
        pytest.skip(message)
    return url


@pytest.fixture(scope="session")
def readonly_role(pg_admin_url: str) -> str:
    from scripts.create_readonly_role import create_role

    return create_role(pg_admin_url, rotate=True)


@pytest.fixture(scope="session")
def serving_url(
    pg_admin_url: str, dbt_fixture: Build, fixture_embeddings: Path, readonly_role: str
) -> Iterator[str]:
    from pipeline.load import serving

    assert dbt_fixture.run.returncode == 0, dbt_fixture.run.output[-3000:]
    name = f"labellens_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(pg_admin_url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')  # type: ignore[arg-type]
    url = make_conninfo(**{**conninfo_to_dict(pg_admin_url), "dbname": name})
    try:
        serving.load(dbt_fixture.db, url, embeddings=fixture_embeddings, log=lambda *_: None)
        yield url
    finally:
        with psycopg.connect(pg_admin_url, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')  # type: ignore[arg-type]


@pytest.fixture(scope="session")
def neo4j_driver() -> Iterator[object]:
    from neo4j import GraphDatabase
    from neo4j.exceptions import DriverError, Neo4jError

    uri, user, password = TEST_NEO4J
    driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=3)
    try:
        driver.verify_connectivity()
    except (DriverError, Neo4jError, OSError) as error:
        driver.close()
        message = f"Test Neo4j not reachable at {uri}: run `docker compose up -d neo4j-test`."
        if os.environ.get("CI"):
            pytest.fail(f"{message} ({error})")
        pytest.skip(message)
    yield driver
    driver.close()


@pytest.fixture(scope="session")
def readonly_url(serving_url: str, readonly_role: str) -> str:
    return make_conninfo(readonly_role, dbname=conninfo_to_dict(serving_url)["dbname"])


@pytest.fixture(scope="session")
def fixture_graph(neo4j_driver: object, dbt_fixture: Build) -> object:
    """The fixture's graph written to the test Neo4j; returns the driver."""
    import duckdb

    from pipeline.load import graph as graph_loader

    with duckdb.connect(str(dbt_fixture.db), read_only=True) as con:
        built = graph_loader.build(con)
    graph_loader.write(neo4j_driver, built, log=lambda _: None)
    return neo4j_driver
