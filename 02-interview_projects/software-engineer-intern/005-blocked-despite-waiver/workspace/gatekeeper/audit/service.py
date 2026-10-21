"""Append-only audit log (docs/architecture.md, "Audit").

``record`` runs in the caller's transaction on purpose: a decision, review or
override and its audit event commit or roll back together. Nothing here
updates or deletes rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, func, insert, select

from gatekeeper.core import clock
from gatekeeper.core.tables import audit_events, teams


def record(
    conn: Connection,
    *,
    action: str,
    actor: str,
    subject_type: str,
    subject_id: int | None,
    team_id: int | None,
    details: dict[str, Any] | None = None,
) -> int:
    return conn.execute(
        insert(audit_events)
        .values(
            action=action,
            actor=actor,
            subject_type=subject_type,
            subject_id=subject_id,
            team_id=team_id,
            details=details or {},
            created_at=clock.now(),
        )
        .returning(audit_events.c.id)
    ).scalar_one()


def list_events(
    conn: Connection,
    *,
    team_id: int | None,
    action: str | None = None,
    subject_type: str | None = None,
    subject_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Events newest first and the total count; ``team_id`` None means every team."""
    a = audit_events.c
    equal = [(a.team_id, team_id), (a.action, action), (a.subject_type, subject_type),
             (a.subject_id, subject_id)]
    filters = [column == value for column, value in equal if value is not None]
    if since is not None:
        filters.append(a.created_at >= since)
    if until is not None:
        filters.append(a.created_at < until)
    total = conn.execute(select(func.count()).select_from(audit_events).where(*filters)).scalar()
    rows = conn.execute(
        select(audit_events, teams.c.slug.label("team"))
        .select_from(audit_events.outerjoin(teams, teams.c.id == a.team_id))
        .where(*filters)
        .order_by(a.created_at.desc(), a.id.desc())
        .limit(limit)
        .offset(offset)
    ).mappings()
    return [dict(row) for row in rows], total
