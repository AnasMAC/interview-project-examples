"""Waiver expiry job (scheduler ``expire_waivers``).

Since 3.4 a waiver expires at its exact ``expires_at`` instant; before that it
lasted until the following midnight UTC (ADR 0003 still describes the old
rule). Matching already ignores a waiver once ``expires_at`` has passed, so
this sweep only makes the status, the audit log and the reports agree.
Pending waivers nobody reviewed in time expire too.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Connection, update

from gatekeeper.audit import service as audit
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import waivers

log = get_logger(__name__)


def expire_due(conn: Connection, *, at: datetime) -> list[int]:
    """Move every pending or approved waiver with ``expires_at <= at`` to expired."""
    w = waivers.c
    rows = conn.execute(
        update(waivers)
        .where(w.status.in_(("pending", "approved")), w.expires_at <= at)
        .values(status="expired")
        .returning(w.id, w.team_id, w.expires_at)
    ).all()
    for row in sorted(rows, key=lambda r: r.id):
        audit.record(
            conn, action="waiver.expired", actor="scheduler", subject_type="waiver",
            subject_id=row.id, team_id=row.team_id,
            details={"expires_at": row.expires_at.isoformat()},
        )
    if rows:
        log.info("waivers.expired", extra={"count": len(rows)})
    return sorted(row.id for row in rows)
