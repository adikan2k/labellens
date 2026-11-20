"""Postgres access for the API: one connection pool, opened with the app.

Queries name the `serving` schema directly instead of setting search_path, and statements are
never auto-prepared: Neon's pooled endpoint (PgBouncer in transaction mode) does not keep
session state between transactions.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

# Raised when the database cannot answer: Neon waking from idle, or down.
UNAVAILABLE = (psycopg.OperationalError, PoolTimeout)
META_TTL_SECONDS = 600

DictConnection = psycopg.Connection[DictRow]


class DatabaseNotConfigured(RuntimeError):
    pass


def _check(conn: DictConnection) -> None:
    """Before lending a connection, make sure it survived Neon suspending the compute."""
    conn.execute("select 1")


@dataclass
class Database:
    pool: ConnectionPool[DictConnection] | None
    _meta: dict[str, str] = field(default_factory=dict)
    _meta_at: float = 0.0

    @classmethod
    def open(cls, url: str | None, *, timeout: float) -> Database:
        if not url:
            return cls(pool=None)
        pool = ConnectionPool(
            url,
            min_size=1,
            max_size=8,
            timeout=timeout,
            open=False,
            connection_class=DictConnection,
            check=_check,
            kwargs={"autocommit": True, "prepare_threshold": None, "row_factory": dict_row},
            name="labellens",
        )
        pool.open(wait=False)
        return cls(pool=pool)

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()

    def connection(self) -> Iterator[DictConnection]:
        if self.pool is None:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        with self.pool.connection() as conn:
            yield conn

    def snapshot_date(self) -> date | None:
        """Snapshot date of the loaded data, cached for ten minutes. None if unavailable."""
        if self.pool is None:
            return None
        if time.monotonic() - self._meta_at > META_TTL_SECONDS or not self._meta:
            try:
                with self.pool.connection() as conn:
                    rows = conn.execute("select key, value from serving.meta").fetchall()
                self._meta = {r["key"]: r["value"] for r in rows}
                self._meta_at = time.monotonic()
            except (*UNAVAILABLE, psycopg.errors.UndefinedTable):
                return None
        value = self._meta.get("snapshot_date")
        return date.fromisoformat(value) if value else None

    def known_snapshot_date(self) -> date | None:
        """The snapshot date if it has been read already, without asking the database: for the
        keep-warm ping, which must not wake it."""
        value = self._meta.get("snapshot_date") if self._meta else None
        return date.fromisoformat(value) if value else None
