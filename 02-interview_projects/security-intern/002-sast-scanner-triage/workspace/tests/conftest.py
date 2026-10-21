"""Shared fixtures for the Bellpost suite.

The suite talks to the Postgres service from ``docker-compose.yml`` (``make up``
or ``make setup``) and uses a database of its own: ``bellpost_test``, derived
from ``BELLPOST_DATABASE_URL`` or set explicitly with
``BELLPOST_TEST_DATABASE_URL``. It is created if missing and migrated to head
with Alembic before the first test; every test that touches the database starts
from empty tables.

The clock is frozen at the world's "today", 2026-05-11 09:00 +01:00
(``tests.helpers.TODAY``), and the two local mocks run as subprocesses on the
ports from the environment (``MOCKHOOK_PORT`` default 8900,
``MOCK_METADATA_PORT`` default 8901) for the duration of the session.

Environment variables are set up before any application module reads settings;
import application code inside the fixtures, not at module import time.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql+psycopg://bellpost:bellpost@127.0.0.1:55432/bellpost"


@pytest.fixture(scope="session")
def _environment(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    """Point the application at the test database, the tmp storage and the mock ports."""
    from sqlalchemy.engine import make_url

    base = (
        os.environ.get("BELLPOST_TEST_DATABASE_URL")
        or os.environ.get("BELLPOST_DATABASE_URL")
        or DEFAULT_DATABASE_URL
    )
    base_url = make_url(base)
    database_name = (base_url.database or "bellpost").rstrip("/")
    if not database_name.endswith("_test"):
        database_name = f"{database_name}_test"
    test_url = base_url.set(database=database_name).render_as_string(hide_password=False)

    storage = tmp_path_factory.mktemp("bellpost")
    os.environ["BELLPOST_ENV"] = "test"
    os.environ["BELLPOST_DATABASE_URL"] = test_url
    os.environ["BELLPOST_TEST_DATABASE_URL"] = test_url
    os.environ["BELLPOST_SECRET_KEY"] = "DEMO-session-secret-not-for-production"
    os.environ["BELLPOST_NOW"] = "2026-05-11T09:00:00+01:00"
    os.environ["BELLPOST_ATTACHMENT_ROOT"] = str(storage / "attachments")
    os.environ["BELLPOST_SPOOL_DIR"] = str(storage / "incoming")
    os.environ["BELLPOST_SPOOL_PROCESSED_DIR"] = str(storage / "processed")
    os.environ["BELLPOST_SPOOL_FAILED_DIR"] = str(storage / "failed")
    os.environ.setdefault("MOCKHOOK_PORT", "8900")
    os.environ.setdefault("MOCK_METADATA_PORT", "8901")
    os.environ.setdefault("MOCKHOOK_LOG", str(storage / "mockhook" / "deliveries.jsonl"))

    from app.config import reload_settings

    reload_settings()
    return {"storage": storage, "database_url": test_url}


@pytest.fixture(scope="session")
def _database(_environment: dict[str, object]) -> str:
    """Create ``bellpost_test`` when missing and run ``alembic upgrade head``."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    database_url = str(_environment["database_url"])
    parsed = make_url(database_url)

    engine = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": parsed.database},
            ).scalar()
            if not exists:
                connection.execute(text('CREATE DATABASE "' + str(parsed.database) + '"'))
    except OperationalError as error:
        pytest.exit(
            f"cannot reach postgres ({parsed.render_as_string(hide_password=False)}): {error}\n"
            "start it with 'make up' (or 'make setup') and try again",
            returncode=1,
        )
    finally:
        engine.dispose()

    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")
    return database_url


@pytest.fixture
def _clean_database(_database: str) -> None:
    """Empty every table before a database test starts."""
    from app.db import get_engine
    from tests.helpers import truncate_all

    truncate_all(get_engine())


@pytest.fixture(autouse=True)
def _frozen_clock(_environment: dict[str, object]) -> Iterator[None]:
    """Freeze the clock at the world's "today" for every test."""
    from app import clock
    from tests.helpers import TODAY

    clock.freeze(TODAY)
    yield
    clock.unfreeze()


@pytest.fixture(autouse=True)
def _restore_settings(_environment: dict[str, object]) -> Iterator[None]:
    """Reset the settings object to the test environment around every test."""
    from app.config import reload_settings

    reload_settings()
    yield
    reload_settings()


@pytest.fixture
def settings():
    """The resolved settings of the test run."""
    from app.config import get_settings

    return get_settings()


@pytest.fixture
def app(_environment: dict[str, object]):
    """A Flask application with ``TESTING`` on."""
    from app import create_app

    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def client(app, _clean_database: None):
    """The test client for :func:`app`."""
    return app.test_client()


@pytest.fixture
def session(app, _clean_database: None) -> Iterator[object]:
    """A SQLAlchemy session on the test database, inside an app context.

    Handlers share this scoped session, so commit before calling the client.
    """
    from app import db

    with app.app_context():
        db_session = db.get_session()
        try:
            yield db_session
        finally:
            db_session.rollback()
            db.remove_session()


@pytest.fixture
def db_session(session):
    """Alias for :func:`session`."""
    return session


@pytest.fixture
def tenant(session):
    """Brightpath Labs, matching the seeded tenant of the demo data."""
    from tests.helpers import build_tenant

    row = build_tenant(
        session,
        slug="brightpath",
        name="Brightpath Labs",
        prefix="BRP",
        plan="growth",
        timezone="Europe/London",
    )
    session.commit()
    return row


@pytest.fixture
def second_tenant(session):
    """Cascade Freight, the second tenant (useful for cross-tenant checks)."""
    from tests.helpers import build_tenant

    row = build_tenant(
        session,
        slug="cascade",
        name="Cascade Freight",
        prefix="CDF",
        plan="scale",
        timezone="America/Denver",
    )
    session.commit()
    return row


@pytest.fixture
def admin_user(session, tenant):
    """Nadia Saleh, admin of Brightpath."""
    from tests.helpers import build_user

    row = build_user(
        session,
        tenant,
        email="nadia.saleh@brightpath.test",
        name="Nadia Saleh",
        role="admin",
    )
    session.commit()
    return row


@pytest.fixture
def agent_user(session, tenant):
    """Owen Blackwood, agent of Brightpath."""
    from tests.helpers import build_user

    row = build_user(
        session,
        tenant,
        email="owen.blackwood@brightpath.test",
        name="Owen Blackwood",
        role="agent",
    )
    session.commit()
    return row


@pytest.fixture
def requester_user(session, tenant):
    """Sana Iqbal, requester of Brightpath."""
    from tests.helpers import build_user

    row = build_user(
        session,
        tenant,
        email="sana.iqbal@brightpath.test",
        name="Sana Iqbal",
        role="requester",
    )
    session.commit()
    return row


@pytest.fixture
def ticket(session, tenant, requester_user):
    """One open ticket owned by :func:`requester_user`."""
    from tests.helpers import build_ticket, build_message

    row = build_ticket(
        session,
        tenant,
        requester=requester_user,
        subject="Parcel is two days late",
        body="Order 1042 has not moved since Tuesday.",
        status="open",
    )
    build_message(
        session,
        row,
        author=requester_user,
        direction="inbound",
        body="Hello, any news on order 1042?",
        message_id="opener@brightpath.test",
    )
    session.commit()
    return row


@pytest.fixture
def agent_token(session, tenant, agent_user) -> str:
    """A bearer token for :func:`agent_user`."""
    from tests.helpers import issue_user_token

    token = issue_user_token(session, tenant, agent_user, name="agent fixture")
    session.commit()
    return token


@pytest.fixture
def admin_token(session, tenant, admin_user) -> str:
    """A bearer token for :func:`admin_user`."""
    from tests.helpers import issue_user_token

    token = issue_user_token(session, tenant, admin_user, name="admin fixture")
    session.commit()
    return token


@pytest.fixture(scope="session")
def mockhook(_environment: dict[str, object]):
    """The local webhook receiver, on ``MOCKHOOK_PORT``."""
    from tests.helpers import start_mockhook

    storage = Path(str(_environment["storage"]))
    server = start_mockhook(
        port=int(os.environ["MOCKHOOK_PORT"]),
        log_path=Path(os.environ["MOCKHOOK_LOG"]),
        output_dir=storage,
    )
    yield server
    server.stop()


@pytest.fixture(scope="session")
def mock_metadata(_environment: dict[str, object]):
    """The local instance-metadata stand-in, on ``MOCK_METADATA_PORT``."""
    from tests.helpers import start_mock_metadata

    storage = Path(str(_environment["storage"]))
    server = start_mock_metadata(
        port=int(os.environ["MOCK_METADATA_PORT"]),
        output_dir=storage,
    )
    yield server
    server.stop()


@pytest.fixture(scope="session")
def mockhook_url(mockhook) -> str:
    """Base URL of the mockhook."""
    return mockhook.url


@pytest.fixture(scope="session")
def mock_metadata_url(mock_metadata) -> str:
    """Base URL of the metadata stand-in."""
    return mock_metadata.url
