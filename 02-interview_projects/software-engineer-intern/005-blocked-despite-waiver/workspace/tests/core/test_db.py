from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from gatekeeper.core import clock
from gatekeeper.core.config import load_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.tables import metadata, teams
from tests.conftest import alembic_config, run_migrations
from tests.factories import TODAY


def _team_count(conn) -> int:
    return conn.execute(select(func.count()).select_from(teams)).scalar_one()


def test_nested_transaction_failure_rolls_back_only_the_inner_block(conn, factory):
    factory.team("payments-api")

    with transaction() as outer:
        outer.execute(teams.insert().values(slug="ledger-core", name="L", callback_secret="s"))
        with pytest.raises(IntegrityError), transaction() as inner:
            inner.execute(teams.insert().values(slug="payments-api", name="P", callback_secret="s"))
        assert outer is inner is conn

    assert _team_count(conn) == 2


def test_frozen_clock_is_aware_utc_and_moves_on_request(frozen_clock):
    assert clock.now() == TODAY and clock.now().tzinfo is UTC

    assert frozen_clock.advance(hours=13) == datetime(2026, 12, 3, 0, 0, tzinfo=UTC)
    clock.freeze(datetime(2026, 12, 3, 9, 0, tzinfo=timezone(timedelta(hours=8))))
    assert clock.now() == datetime(2026, 12, 3, 1, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        clock.freeze(datetime(2026, 12, 3, 9, 0))


def test_unfrozen_clock_follows_the_wall_clock():
    clock.unfreeze()

    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
    with pytest.raises(RuntimeError):
        clock.advance(seconds=1)


def test_gate_now_pins_the_dev_clock_below_freeze_and_never_in_prod(monkeypatch):
    monkeypatch.setenv("GATE_NOW", "2026-12-02T12:00:00+01:00")
    settings = load_settings()
    assert settings.dev_now == TODAY
    monkeypatch.setattr(clock, "get_settings", lambda: settings)
    clock.unfreeze()
    assert clock.now() == TODAY
    clock.freeze(TODAY + timedelta(hours=1))  # a test's (or script's) own clock wins
    assert clock.now() == TODAY + timedelta(hours=1)

    monkeypatch.setenv("GATE_NOW", "2026-12-02T11:00:00")
    with pytest.raises(ValueError, match="offset"):
        load_settings()
    monkeypatch.setenv("GATE_NOW", "2026-12-02T11:00:00Z")
    monkeypatch.setenv("GATE_ENV", "prod")
    with pytest.raises(ValueError, match="dev-only"):
        load_settings()
    monkeypatch.setenv("GATE_NOW", "")
    assert load_settings().dev_now is None


def test_migrations_at_head_match_the_table_metadata(conn):
    diff = compare_metadata(MigrationContext.configure(conn), metadata)

    assert diff == []


def test_migrations_run_down_and_up_and_backfill_callback_secrets(conn):
    command.downgrade(alembic_config(conn), "base")
    assert conn.execute(text("SELECT to_regclass('public.teams')")).scalar() is None

    run_migrations(conn, "0001")
    conn.execute(text("INSERT INTO teams (slug, name) VALUES ('kyc-platform', 'KYC Platform')"))
    run_migrations(conn)

    secret = conn.execute(text("SELECT callback_secret FROM teams")).scalar_one()
    assert secret.startswith("DEMO-whsec-kyc-platform-") and len(secret) == 36
    assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"
