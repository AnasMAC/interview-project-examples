"""SQLite connections and transactions.

Rules (see docs/architecture.md, "Transactions"):

* one connection per thread; never share a connection across threads;
* connections are in autocommit mode, so writes happen inside ``transaction()``;
* library functions never commit; the caller (CLI command, API handler) owns
  the transaction. A nested ``transaction()`` becomes a savepoint.
"""

from __future__ import annotations

import itertools
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ledger.core.config import Settings

_savepoints = itertools.count(1)


def connect(path: Path | str, *, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    """Open a connection with WAL, foreign keys and a busy timeout.

    ``":memory:"`` is accepted for throwaway use; it has no WAL.
    """
    memory = str(path) == ":memory:"
    if not memory:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    conn.execute("PRAGMA foreign_keys = ON")
    if not memory:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def open_db(settings: Settings) -> sqlite3.Connection:
    return connect(settings.db_path, busy_timeout_ms=settings.busy_timeout_ms)


@contextmanager
def transaction(conn: sqlite3.Connection, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
    """Commit on success, roll back on any exception.

    ``immediate=True`` (the default) takes the write lock at BEGIN, so two
    concurrent writers queue on the busy timeout instead of failing with
    "database is locked" when a read transaction upgrades. Use
    ``immediate=False`` for a read-only snapshot over several queries.
    """
    if conn.in_transaction:
        name = f"sp_{next(_savepoints)}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            raise
        conn.execute(f"RELEASE {name}")
        return
    conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield conn
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
