"""The ask agent's read-only role and the API's app schema, on the test Postgres."""

from __future__ import annotations

from pathlib import Path

import psycopg
import pytest

from pipeline.load import serving
from pipeline.tests.support import Build
from scripts import create_readonly_role as script


def _connect(url: str) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=True, prepare_threshold=None)


def test_role_name_matches_the_loader() -> None:
    assert script.ROLE == serving.PRODUCTION_READONLY_ROLE


def test_reads_exactly_the_public_tables(readonly_url: str) -> None:
    with _connect(readonly_url) as pg:
        for table in serving.READONLY_TABLES:
            row = pg.execute(f"select count(*) from serving.{table}").fetchone()  # type: ignore[arg-type]
            assert row and row[0] > 0, table
        for table in ("serving.stats", "serving.meta", "app.ask_runs"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                pg.execute(f"select * from {table}")  # type: ignore[arg-type]


def test_cannot_write_even_in_a_read_write_transaction(readonly_url: str) -> None:
    with _connect(readonly_url) as pg:
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            pg.execute("delete from serving.products")
        with pg.transaction():
            pg.execute("set transaction read write")
            for statement in (
                "delete from serving.products",
                "create table serving.x (a int)",
                "create table public.x (a int)",
            ):
                # A savepoint per attempt, so the next one runs.
                with pytest.raises(psycopg.errors.InsufficientPrivilege), pg.transaction():
                    pg.execute(statement)  # type: ignore[arg-type]


def test_role_defaults_and_attributes(readonly_url: str) -> None:
    with _connect(readonly_url) as pg:
        assert pg.execute("show statement_timeout").fetchone() == ("3s",)
        assert pg.execute("show default_transaction_read_only").fetchone() == ("on",)
        row = pg.execute(
            "select rolsuper, rolcreatedb, rolcreaterole, rolinherit from pg_roles "
            "where rolname = current_user"
        ).fetchone()
        assert row == (False, False, False, False)
        memberships = pg.execute(
            "select count(*) from pg_auth_members m join pg_roles r on r.oid = m.member "
            "where r.rolname = current_user"
        ).fetchone()
        assert memberships == (0,)


def test_grants_and_run_log_survive_a_reload(
    serving_url: str, readonly_url: str, dbt_fixture: Build, fixture_embeddings: Path
) -> None:
    with _connect(serving_url) as pg:
        pg.execute("insert into app.ask_runs (client_hash, outcome) values ('test', 'answer')")
    serving.load(dbt_fixture.db, serving_url, embeddings=fixture_embeddings, log=lambda *_: None)
    with _connect(readonly_url) as pg:
        assert pg.execute("select count(*) > 0 from serving.explainers").fetchone() == (True,)
    with _connect(serving_url) as pg:
        row = pg.execute("select count(*) from app.ask_runs where client_hash = 'test'").fetchone()
        assert row == (1,)
        pg.execute("delete from app.ask_runs where client_hash = 'test'")


def test_existing_role_needs_rotate(pg_admin_url: str, readonly_role: str) -> None:
    with pytest.raises(SystemExit, match="--rotate"):
        script.create_role(pg_admin_url)


def test_role_url_swaps_only_the_credentials() -> None:
    url = script.role_url(
        "postgresql://owner:secret@ep-x-pooler.neon.tech/neondb?sslmode=require&channel_binding=require",
        "labellens_readonly",
        "p/w+",
    )
    assert url == (
        "postgresql://labellens_readonly:p%2Fw%2B@ep-x-pooler.neon.tech/neondb"
        "?sslmode=require&channel_binding=require"
    )


def test_write_env_fills_replaces_or_refuses(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nDATABASE_URL_READONLY=\nB=2\n", "utf-8")
    script.write_env(env, "DATABASE_URL_READONLY", "postgresql://x", replace=False)
    assert env.read_text("utf-8") == "A=1\nDATABASE_URL_READONLY=postgresql://x\nB=2\n"
    with pytest.raises(SystemExit, match="already set"):
        script.write_env(env, "DATABASE_URL_READONLY", "postgresql://y", replace=False)
    script.write_env(env, "DATABASE_URL_READONLY", "postgresql://y", replace=True)
    assert "DATABASE_URL_READONLY=postgresql://y\n" in env.read_text("utf-8")

    fresh = tmp_path / "new.env"
    script.write_env(fresh, "DATABASE_URL_READONLY", "postgresql://z", replace=False)
    assert fresh.read_text("utf-8") == "DATABASE_URL_READONLY=postgresql://z\n"
