"""Abstract database backend interface for future PostgreSQL migration.

Current state
-------------
All stores use SQLite via ``db_utils.sqlite_connect``.  This module defines
the contract that a PostgreSQL (or any other) backend must satisfy so the
stores can be switched over with minimal code changes.

Production PostgreSQL note
--------------------------
For async FastAPI deployments, prefer **asyncpg** + a connection-pool
(e.g. ``asyncpg.create_pool``).  The synchronous ``execute / fetchone /
fetchall`` surface below would be wrapped by an async adapter or replaced
with an async abstract base (``async def execute(...)``) once the migration
is underway.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from app.services.db_utils import sqlite_connect


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class DatabaseBackend(ABC):
    """Minimal contract every database backend must implement."""

    @abstractmethod
    @contextmanager
    def connect(self, *, readonly: bool = False) -> Iterator[Any]:
        """Yield something that exposes *execute*, *fetchone*, *fetchall*."""
        ...

    @abstractmethod
    def execute(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        """Execute a statement and return a cursor / result handle."""
        ...

    @abstractmethod
    def fetchone(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> dict | None:
        """Execute and return a single row as a dict, or *None*."""
        ...

    @abstractmethod
    def fetchall(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        """Execute and return all rows as a list of dicts."""
        ...


# ---------------------------------------------------------------------------
# SQLite implementation (current default)
# ---------------------------------------------------------------------------

class SQLiteBackend(DatabaseBackend):
    """SQLite backend backed by ``db_utils.sqlite_connect``."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Iterator[sqlite3.Connection]:
        with sqlite_connect(self._db_path, readonly=readonly) as conn:
            yield conn

    def execute(self, conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        return conn.execute(sql, params)

    def fetchone(self, conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> dict | None:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# PostgreSQL implementation (TODO -- stub for future migration)
# ---------------------------------------------------------------------------

class PostgreSQLBackend(DatabaseBackend):
    """Placeholder for a PostgreSQL backend.

    Implementation plan
    ~~~~~~~~~~~~~~~~~~~
    1. Use **asyncpg** (``pip install asyncpg``) for async workloads or
       **psycopg[binary]** (v3) for synchronous ones.
    2. Replace ``?`` parameter placeholders with ``$1, $2, ...`` (asyncpg)
       or ``%s`` (psycopg).
    3. Use a connection pool (``asyncpg.create_pool`` or
       ``psycopg_pool.ConnectionPool``) instead of opening a connection per
       request.
    4. Run the migration script ``app/migrations/001_initial.sql`` to
       create the schema.
    """

    def __init__(self, dsn: str) -> None:  # noqa: D401
        self._dsn = dsn

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Iterator[Any]:
        raise NotImplementedError("PostgreSQL backend not yet implemented")

    def execute(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        raise NotImplementedError("PostgreSQL backend not yet implemented")

    def fetchone(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> dict | None:
        raise NotImplementedError("PostgreSQL backend not yet implemented")

    def fetchall(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        raise NotImplementedError("PostgreSQL backend not yet implemented")
