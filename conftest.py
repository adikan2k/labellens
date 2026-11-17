"""Session fixtures shared by pipeline and API tests.

- dbt_fixture: one dbt build of the committed fixture per test session.
- serving_url: a throwaway Postgres database with the fixture loaded into the serving schema.
  Needs the test Postgres (docker compose up -d postgres). Locally the database tests are
  skipped with that hint when it is not running; in CI (CI=true) they fail instead.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from pipeline.tests.support import FIXTURE_VARS, Build, run_dbt, test_database_url


@pytest.fixture(scope="session")
def dbt_fixture(tmp_path_factory: pytest.TempPathFactory) -> Build:
    tmp = tmp_path_factory.mktemp("dbt")
    return Build(run_dbt("build", tmp, FIXTURE_VARS), tmp / "fixture.duckdb", tmp)


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
def serving_url(pg_admin_url: str, dbt_fixture: Build) -> Iterator[str]:
    from pipeline.load import serving

    assert dbt_fixture.run.returncode == 0, dbt_fixture.run.output[-3000:]
    name = f"labellens_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(pg_admin_url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')  # type: ignore[arg-type]
    url = make_conninfo(**{**conninfo_to_dict(pg_admin_url), "dbname": name})
    try:
        serving.load(dbt_fixture.db, url, log=lambda *_: None)
        yield url
    finally:
        with psycopg.connect(pg_admin_url, autocommit=True) as admin:
            admin.execute(f'drop database if exists "{name}" with (force)')  # type: ignore[arg-type]
