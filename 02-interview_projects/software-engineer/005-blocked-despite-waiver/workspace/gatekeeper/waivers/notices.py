"""Expiry notices (scheduler ``send_expiry_notices``).

An approved waiver that expires within the next 72 hours and was not noticed
yet gets one ``waiver.expiring`` callback to its team's ``notify_url``, sent
while the local time in the **team's timezone** is in hour
``GATE_WAIVER_NOTICE_HOUR`` (09). The scheduler runs every 30 s, so the first
run in that hour enqueues it and sets ``expiry_notice_sent_at``; later runs
skip it. Teams without a ``notify_url`` get nothing (and are retried, in case
one is configured before the waiver expires).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, select, update

from gatekeeper.callbacks import service as callbacks
from gatekeeper.core.config import get_settings
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import teams, waivers
from gatekeeper.waivers.service import waiver_view

log = get_logger(__name__)

NOTICE_WINDOW = timedelta(hours=72)


def send_expiry_notices(conn: Connection, *, at: datetime, notice_hour: int | None = None) -> int:
    """Enqueue the notices due at ``at``; returns how many were enqueued."""
    hour = notice_hour if notice_hour is not None else get_settings().waiver_notice_hour
    w = waivers.c
    due = conn.execute(
        select(w.id, w.team_id, teams.c.slug, teams.c.timezone, teams.c.notify_url)
        .join(teams, teams.c.id == w.team_id)
        .where(
            w.status == "approved",
            w.expiry_notice_sent_at.is_(None),
            w.expires_at > at,
            w.expires_at <= at + NOTICE_WINDOW,
            teams.c.notify_url.is_not(None),
        )
        .order_by(w.id)
        .with_for_update(of=waivers, skip_locked=True)
    ).all()
    sent = 0
    for row in due:
        if at.astimezone(ZoneInfo(row.timezone)).hour != hour:
            continue
        conn.execute(update(waivers).where(w.id == row.id).values(expiry_notice_sent_at=at))
        callbacks.enqueue(
            conn, team_id=row.team_id, event="waiver.expiring", url=row.notify_url,
            payload={"event": "waiver.expiring", "team": row.slug,
                     "waiver": waiver_view(conn, row.id)},
        )
        sent += 1
    if sent:
        log.info("waivers.expiry_notices_sent", extra={"count": sent})
    return sent
