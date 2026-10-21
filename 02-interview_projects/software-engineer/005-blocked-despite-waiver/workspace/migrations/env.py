"""Alembic environment.

The URL comes from DATABASE_URL (gatekeeper.core.config). Tests pass an open
connection through ``config.attributes["connection"]`` so migrations run
inside the test session's connection.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from gatekeeper.core.config import get_settings
from gatekeeper.core.tables import metadata

config = context.config
if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url, target_metadata=metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(get_settings().database_url)
    try:
        with engine.connect() as conn:
            _run(conn)
            conn.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
