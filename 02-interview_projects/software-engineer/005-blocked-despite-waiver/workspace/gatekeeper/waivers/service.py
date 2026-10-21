"""Waiver requests, security review and their use during evaluation.

Lifecycle (docs/architecture.md, "Waivers")::

    pending  -> approved | rejected   (security reviewer)
    approved -> revoked               (reviewer or the owning team; the route checks who)
    pending | approved -> expired     (scheduler, waivers.expiry)

Any other transition is 409 ``invalid_transition``. Every change writes its
audit event in the same transaction.
"""

from __future__ import annotations

import dataclasses
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Row, func, insert, select, update

from gatekeeper.audit import service as audit
from gatekeeper.core import clock
from gatekeeper.core.config import get_settings
from gatekeeper.core.contracts import RuleResult
from gatekeeper.core.errors import Conflict, NotFound, ValidationFailed
from gatekeeper.core.tables import services, teams, waivers
from gatekeeper.waivers.matching import best_match, canonical_rule
from gatekeeper.waivers.schemas import WaiverSchema

_VIOLATED = ("warn", "block")
_view_schema = WaiverSchema()

# Approved waivers change a few times a day; evaluations read them for every
# violated result. Candidates are kept per (team, rule) for a while so a burst
# of pipelines from one team does not repeat the same query (GATE-405 follow-up).
CANDIDATE_TTL = timedelta(minutes=15)
_candidates: dict[tuple[int, str], tuple[datetime, list[Row]]] = {}
_candidates_lock = threading.Lock()


def _view_query():
    return select(
        waivers, teams.c.slug.label("team"), services.c.slug.label("service")
    ).select_from(
        waivers.join(teams, teams.c.id == waivers.c.team_id).outerjoin(
            services, services.c.id == waivers.c.service_id
        )
    )


def get_row(conn: Connection, waiver_id: int, *, lock: bool = False) -> Row:
    query = select(waivers).where(waivers.c.id == waiver_id)
    row = conn.execute(query.with_for_update() if lock else query).first()
    if row is None:
        raise NotFound(f"waiver {waiver_id} not found")
    return row


def waiver_view(conn: Connection, waiver_id: int) -> dict[str, Any]:
    row = conn.execute(_view_query().where(waivers.c.id == waiver_id)).mappings().first()
    if row is None:
        raise NotFound(f"waiver {waiver_id} not found")
    return _view_schema.dump(row)


def list_waivers(
    conn: Connection, *, team_id: int | None, status: str | None = None,
    service: str | None = None, rule: str | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    w = waivers.c
    equal = [(w.team_id, team_id), (w.status, status), (services.c.slug, service),
             (w.rule, canonical_rule(rule) if rule else None)]
    filters = [column == value for column, value in equal if value is not None]
    query = _view_query().where(*filters)
    total = conn.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = conn.execute(query.order_by(w.created_at.desc(), w.id.desc()).limit(limit)
                        .offset(offset)).mappings()
    return _view_schema.dump(rows, many=True), total


def _audit(conn: Connection, row: Row, action: str, actor: str, note: str | None) -> None:
    audit.record(
        conn, action=action, actor=actor, subject_type="waiver", subject_id=row.id,
        team_id=row.team_id,
        details={"rule": row.rule, "service_id": row.service_id,
                 "expires_at": row.expires_at.isoformat(), "note": note},
    )


def request_waiver(
    conn: Connection, *, team_id: int, service_id: int | None, rule: str,
    version_range: str | None, reason: str, expires_at: datetime, actor: str,
    max_days: int | None = None,
) -> dict[str, Any]:
    now = clock.now()
    max_days = max_days if max_days is not None else get_settings().waiver_max_days
    if expires_at <= now:
        raise ValidationFailed("expires_at must be in the future",
                               details={"expires_at": ["must be in the future"]})
    if expires_at > now + timedelta(days=max_days):
        raise ValidationFailed(f"waivers last at most {max_days} days", code="waiver_too_long",
                               details={"max_days": max_days})
    if service_id is not None:
        owner = conn.execute(select(services.c.team_id).where(services.c.id == service_id)).scalar()
        if owner != team_id:
            raise ValidationFailed(f"service {service_id} not found", code="unknown_service")
    row = conn.execute(
        insert(waivers)
        .values(team_id=team_id, service_id=service_id, rule=canonical_rule(rule),
                version_range=version_range, reason=reason, requested_by=actor,
                status="pending", expires_at=expires_at, created_at=now)
        .returning(waivers)
    ).one()
    _audit(conn, row, "waiver.requested", actor, None)
    return waiver_view(conn, row.id)


def _review(
    conn: Connection, waiver_id: int, *, to: str, allowed_from: tuple[str, ...], actor: str,
    note: str | None,
) -> dict[str, Any]:
    row = get_row(conn, waiver_id, lock=True)
    now = clock.now()
    if row.status not in allowed_from or row.expires_at <= now:
        state = "expired" if row.status in allowed_from else row.status
        raise Conflict(f"waiver {waiver_id} is {state} and cannot become {to}",
                       code="invalid_transition", details={"status": row.status, "to": to})
    values: dict[str, Any] = {"status": to}
    if to != "revoked":  # the approval stays on the row; the revocation is in the audit log
        values.update(reviewed_by=actor, reviewed_at=now, review_note=note)
    conn.execute(update(waivers).where(waivers.c.id == waiver_id).values(**values))
    _audit(conn, row, f"waiver.{to}", actor, note)
    return waiver_view(conn, waiver_id)


def approve(conn: Connection, *, waiver_id: int, actor: str, note: str | None = None
            ) -> dict[str, Any]:
    return _review(conn, waiver_id, to="approved", allowed_from=("pending",), actor=actor,
                   note=note)


def reject(conn: Connection, *, waiver_id: int, actor: str, note: str) -> dict[str, Any]:
    return _review(conn, waiver_id, to="rejected", allowed_from=("pending",), actor=actor,
                   note=note)


def revoke(conn: Connection, *, waiver_id: int, actor: str, note: str | None = None
           ) -> dict[str, Any]:
    return _review(conn, waiver_id, to="revoked", allowed_from=("approved",), actor=actor,
                   note=note)


def apply_waivers(
    conn: Connection, *, team_id: int, service_id: int, version: str | None,
    results: list[RuleResult],
) -> list[RuleResult]:
    """Violated results covered by a waiver become ``warn`` with ``waiver_id``.

    Reads only: ingest writes the ``waiver.applied`` audit events once the
    evaluation row exists, and dry runs call this too.
    """
    violated = {canonical_rule(r.rule) for r in results if r.outcome in _VIOLATED}
    if not violated:
        return list(results)
    now = clock.now()
    candidates = [row for rule in sorted(violated)
                  for row in _approved_for(conn, team_id=team_id, service_id=service_id,
                                           rule=rule, now=now)]
    applied = []
    for result in results:
        match = None
        if result.outcome in _VIOLATED:
            match = best_match(candidates, team_id=team_id, service_id=service_id,
                               rule=result.rule, version=version, at=now)
        if match is None:
            applied.append(result)
            continue
        applied.append(dataclasses.replace(
            result, outcome="warn", waiver_id=match.id, message=f"waived: {result.message}"))
    return applied


def _approved_for(conn: Connection, *, team_id: int, service_id: int, rule: str,
                  now: datetime) -> list[Row]:
    """Approved, unexpired waivers of the team for one canonical rule (cached)."""
    key = (team_id, rule)
    with _candidates_lock:
        cached = _candidates.get(key)
    if cached is not None and now - cached[0] < CANDIDATE_TTL:
        return cached[1]
    w = waivers.c
    rows = conn.execute(
        select(waivers).where(
            w.team_id == team_id, w.status == "approved", w.expires_at > now, w.rule == rule,
            (w.service_id.is_(None)) | (w.service_id == service_id),
        ).order_by(w.id)
    ).all()
    with _candidates_lock:
        _candidates[key] = (now, rows)
    return rows
