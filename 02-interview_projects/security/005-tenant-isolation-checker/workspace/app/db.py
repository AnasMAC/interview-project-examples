"""SQLAlchemy engine and session lifecycle.

One engine per process, built lazily from ``BELLPOST_DATABASE_URL``. Web
requests share a thread-local session through :func:`get_session`; the session
is closed by the Flask teardown hook registered in :func:`init_app`. Scripts,
the ingest worker and tests use :func:`session_scope`, which commits on
success and rolls back on error.

Two older modules (``app/legacy/ticket_search.py`` and the archived importer
under ``tools/csv-import/``) predate the ORM and import :func:`get_conn`, which
hands out a raw DBAPI connection. New code uses the session API.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flask import Flask
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base class for every Bellpost model."""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_scoped: scoped_session[Session] | None = None


def get_engine() -> Engine:
    """Return the process engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the ``sessionmaker`` bound to the engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


def _scoped_session() -> scoped_session[Session]:
    global _scoped
    if _scoped is None:
        _scoped = scoped_session(get_session_factory())
    return _scoped


def get_session() -> Session:
    """Return the session for the current thread.

    Callers commit explicitly; the Flask teardown hook removes the session at
    the end of the request.
    """
    return _scoped_session()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager: commit on success, roll back on error, always close."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        remove_session()


def remove_session() -> None:
    """Close and forget the thread-local session."""
    if _scoped is not None:
        _scoped.remove()


def get_conn() -> Any:
    """Return a raw DBAPI connection (legacy modules only)."""
    return get_engine().raw_connection()


def check_database() -> bool:
    """Return ``True`` when the database answers a trivial query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


def dispose_engine() -> None:
    """Dispose the engine and drop cached sessions (tests, exit paths)."""
    global _engine, _session_factory, _scoped
    remove_session()
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _scoped = None


def init_app(app: Flask) -> None:
    """Register the request teardown that closes the session."""

    @app.teardown_appcontext
    def _teardown(exception: BaseException | None) -> None:
        remove_session()
