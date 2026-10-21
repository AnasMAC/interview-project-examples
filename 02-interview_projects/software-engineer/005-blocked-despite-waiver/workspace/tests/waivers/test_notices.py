from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from gatekeeper.core.tables import callback_outbox, waivers
from gatekeeper.waivers.notices import send_expiry_notices


def _team(factory, slug, timezone):
    return factory.team(slug, timezone=timezone, notify_url=f"http://ci-mock:9100/notify/{slug}")


def _utc(day, hour):
    return datetime(2026, 12, day, hour, tzinfo=UTC)


@pytest.mark.parametrize(("slug", "timezone", "notice_at", "too_early"), [
    ("settlement-sg", "Asia/Singapore", _utc(3, 1), _utc(2, 11)),  # 09:00 SGT = 01:00 UTC
    ("payments-api", "Europe/London", _utc(3, 9), _utc(3, 1)),  # GMT in December
])
def test_one_notice_at_nine_in_the_team_timezone(
    conn, factory, slug, timezone, notice_at, too_early
):
    team = _team(factory, slug, timezone)
    waiver = factory.waiver(team=team, expires_at=_utc(4, 12))

    assert send_expiry_notices(conn, at=too_early) == 0
    assert send_expiry_notices(conn, at=notice_at) == 1
    assert send_expiry_notices(conn, at=notice_at + timedelta(minutes=30)) == 0
    outbox = conn.execute(select(callback_outbox)).one()
    assert (outbox.event, outbox.url) == ("waiver.expiring", f"http://ci-mock:9100/notify/{slug}")
    assert outbox.payload["team"] == slug
    assert outbox.payload["waiver"]["id"] == waiver.id
    sent_at = conn.execute(select(waivers.c.expiry_notice_sent_at)).scalar()
    assert sent_at == notice_at


def test_no_notice_outside_the_window_or_without_notify_url(conn, factory):
    london = _team(factory, "payments-api", "Europe/London")
    factory.waiver(team=london, expires_at=_utc(3, 9) + timedelta(hours=72, seconds=1))
    factory.waiver(team=london, status="pending", expires_at=_utc(4, 0))
    factory.waiver(team=factory.team("fx-rates"), expires_at=_utc(4, 0))  # no notify_url

    assert send_expiry_notices(conn, at=_utc(3, 9)) == 0
