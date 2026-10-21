"""Shared fixtures; docs/architecture.md, "Test helpers", explains them.

* The database named by DATABASE_URL must end in ``_test``; it is created if
  missing, wiped and migrated to head with the real migrations once per run.
* ``conn``: one connection in an outer transaction rolled back after the test;
  every ``db.transaction()`` in the code (and in ``client`` requests) runs on
  it as a SAVEPOINT. ``committed_engine`` (``@pytest.mark.committed``) commits
  for real and truncates every table afterwards.
* The clock is frozen at TODAY (2026-12-02 11:00 UTC) in every test.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url

from gatekeeper.core import clock, db
from gatekeeper.core.app import create_app
from gatekeeper.core.config import REPO_ROOT, get_settings
from gatekeeper.core.tables import metadata
from tests.factories import TODAY, Factory


def _prepare_database(url: str) -> None:
    target = make_url(url)
    if not (target.database or "").endswith("_test"):
        pytest.exit(f"refusing to run tests against {target.database!r}: use a *_test database")
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        admin.dispose()


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.attributes.update(connection=connection, configure_logger=False)
    return cfg


def run_migrations(connection: Connection, revision: str = "head") -> None:
    command.upgrade(alembic_config(connection), revision)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _prepare_database(get_settings().database_url)
    eng = db.get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        run_migrations(conn)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    connection = engine.connect()
    outer = connection.begin()
    try:
        with db.bind(connection):
            yield connection
    finally:
        outer.rollback()
        connection.close()


@pytest.fixture
def committed_engine(engine: Engine) -> Iterator[Engine]:
    yield engine
    names = ", ".join(t.name for t in metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def frozen_clock():
    clock.freeze(TODAY)
    yield clock
    clock.unfreeze()


@pytest.fixture(scope="session")
def app() -> Flask:
    return create_app()


@pytest.fixture
def client(app: Flask, conn: Connection) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def factory(conn: Connection) -> Factory:
    return Factory(conn)

