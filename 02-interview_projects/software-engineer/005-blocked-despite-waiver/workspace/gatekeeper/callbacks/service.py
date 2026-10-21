"""Callback outbox writes (docs/architecture.md, "Callbacks and outbox").

``enqueue`` runs in the caller's transaction, so a callback exists exactly
when the decision or notice that caused it was committed. Delivery happens
later in the scheduler (``callbacks.delivery``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, insert, select, update

from gatekeeper.audit import service as audit
from gatekeeper.core import clock
from gatekeeper.core.errors import NotFound
from gatekeeper.core.tables import callback_outbox


def enqueue(
    conn: Connection,
    *,
    team_id: int,
    event: str,
    url: str,
    payload: dict[str, Any],
    evaluation_id: int | None = None,
) -> int:
    now = clock.now()
    return conn.execute(
        insert(callback_outbox)
        .values(team_id=team_id, evaluation_id=evaluation_id, event=event, url=url,
                payload=payload, status="pending", attempts=0, next_attempt_at=now,
                created_at=now)
        .returning(callback_outbox.c.id)
    ).scalar_one()


def replay(conn: Connection, *, outbox_id: int, actor: str) -> None:
    """Send a callback again from scratch: pending, attempts 0, due now."""
    o = callback_outbox.c
    row = conn.execute(select(callback_outbox).where(o.id == outbox_id).with_for_update()).first()
    if row is None:
        raise NotFound(f"callback {outbox_id} not found")
    conn.execute(
        update(callback_outbox)
        .where(o.id == outbox_id)
        .values(status="pending", attempts=0, next_attempt_at=clock.now(), last_error=None,
                delivered_at=None)
    )
    audit.record(
        conn,
        action="callback.replayed",
        actor=actor,
        subject_type="callback",
        subject_id=outbox_id,
        team_id=row.team_id,
        details={"event": row.event, "attempts": row.attempts, "last_error": row.last_error,
                 "previous_status": row.status},
    )
