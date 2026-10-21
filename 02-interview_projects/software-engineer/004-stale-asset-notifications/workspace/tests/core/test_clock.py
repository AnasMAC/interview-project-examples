from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from atlas.core import clock
from tests.factories import TODAY


def test_tests_run_at_world_today(frozen_clock):
    assert clock.now() == TODAY
    assert frozen_clock.advance(hours=2) == TODAY + timedelta(hours=2)


def test_local_date_uses_the_org_timezone():
    late = datetime(2026, 11, 5, 3, 30, tzinfo=UTC)  # 22:30 on the 4th in Toronto
    assert clock.local_date("America/Toronto", late) == date(2026, 11, 4)
    assert clock.local_date("Pacific/Auckland", late) == date(2026, 11, 5)


def test_frozen_restores_previous_value():
    with clock.frozen(datetime(2026, 11, 1, 6, 0, tzinfo=timezone(timedelta(hours=1)))):
        assert clock.now() == datetime(2026, 11, 1, 5, 0, tzinfo=UTC)
    assert clock.now() == TODAY


def test_freeze_rejects_naive_datetimes():
    with pytest.raises(ValueError, match="aware"):
        clock.freeze(datetime(2026, 11, 5, 9, 30))


def test_isoformat_is_utc_with_z():
    assert clock.isoformat(TODAY) == "2026-11-05T14:30:00Z"


def test_dev_clock_starts_at_atlas_now_and_keeps_running(settings, monkeypatch):
    settings.ATLAS_NOW = "2026-11-05T14:30:00Z"
    monkeypatch.setattr(clock, "_offset", None)
    clock.unfreeze()
    first = clock.now()
    assert abs(first - TODAY) < timedelta(seconds=5)
    assert clock.now() >= first
    clock.freeze(TODAY - timedelta(days=1))  # a frozen clock (tests, the seed) still wins
    assert clock.now() == TODAY - timedelta(days=1)


def test_dev_clock_off_means_real_time(settings, monkeypatch):
    settings.ATLAS_NOW = ""
    monkeypatch.setattr(clock, "_offset", None)
    clock.unfreeze()
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
