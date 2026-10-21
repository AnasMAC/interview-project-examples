"""Engine and the transaction helper.

Rules (docs/architecture.md, "Transactions"):

* HTTP handlers, scheduler jobs and CLI commands open the unit of work with
  ``with transaction() as conn:``; service functions take ``conn`` as their
  first argument and never commit or open a transaction of their own.
* ``transaction()`` is re-entrant: inside an open one it yields the same
  connection under a SAVEPOINT, so a nested call can fail on its own.
* Tests bind one connection (``bind``) that is rolled back afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine

from gatekeeper.core.config import get_settings

_current: ContextVar[Connection | None] = ContextVar("gatekeeper_connection", default=None)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"application_name": f"gatekeeper-{settings.service_name}"},
    )


@contextmanager
def transaction() -> Iterator[Connection]:
    conn = _current.get()
    if conn is not None:
        with conn.begin_nested():
            yield conn
        return
    with get_engine().begin() as conn:
        token = _current.set(conn)
        try:
            yield conn
        finally:
            _current.reset(token)


@contextmanager
def bind(conn: Connection) -> Iterator[Connection]:
    """Route every ``transaction()`` in this context through ``conn``."""
    token = _current.set(conn)
    try:
        yield conn
    finally:
        _current.reset(token)
