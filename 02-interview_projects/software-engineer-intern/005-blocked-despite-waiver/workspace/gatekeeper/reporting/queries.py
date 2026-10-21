"""Scorecard and export queries (SQLAlchemy Core, one grouped query per metric).

A scorecard covers the evaluations created in ``[since, until)``; waiver
figures describe the waivers as they stand at ``until``. ``team_id=None``
means every team (reviewers).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Select, func, select
from sqlalchemy.dialects.postgresql import JSONB

from gatekeeper.core.tables import evaluations, policies, services, teams, waivers

EXPIRING_SOON_DAYS = 7


def _scoped(query: Select, column: sa.Column, team_id: int | None) -> Select:
    return query if team_id is None else query.where(column == team_id)


def decision_counts(
    conn: Connection, *, team_id: int | None, since: datetime, until: datetime
) -> dict[int, dict[str, int]]:
    e = evaluations.c
    query = (
        select(
            e.team_id,
            func.count().label("total"),
            func.count().filter(e.decision == "block").label("block"),
            func.count().filter(e.decision == "warn").label("warn"),
        )
        .where(e.created_at >= since, e.created_at < until)
        .group_by(e.team_id)
    )
    rows = conn.execute(_scoped(query, e.team_id, team_id))
    return {r.team_id: {"total": r.total, "block": r.block, "warn": r.warn} for r in rows}


def waiver_stats(
    conn: Connection, *, team_id: int | None, since: datetime, until: datetime
) -> dict[int, dict[str, Any]]:
    w = waivers.c
    active = sa.and_(w.status == "approved", w.expires_at > until)
    at = sa.literal(until, sa.DateTime(timezone=True))
    age_days = func.extract("epoch", at - w.created_at) / 86400.0
    query = select(
        w.team_id,
        func.count().filter(w.created_at >= since, w.created_at < until).label("requested"),
        func.count().filter(active).label("active"),
        func.count().filter(w.status == "pending").label("pending"),
        func.count()
        .filter(active, w.expires_at <= until + timedelta(days=EXPIRING_SOON_DAYS))
        .label("expiring_soon"),
        func.percentile_cont(0.5).within_group(age_days).filter(active).label("median_age"),
        func.max(age_days).filter(active).label("oldest_age"),
    ).group_by(w.team_id)
    rows = conn.execute(_scoped(query, w.team_id, team_id))
    return {
        r.team_id: _waiver_dict(
            r.requested, r.active, r.pending, r.expiring_soon, r.median_age, r.oldest_age
        )
        for r in rows
    }


def empty_waiver_stats() -> dict[str, Any]:
    return _waiver_dict(0, 0, 0, 0, None, None)


def _waiver_dict(requested, active, pending, expiring, median, oldest) -> dict[str, Any]:
    return {
        "requested_in_window": requested,
        "active": active,
        "pending": pending,
        "expiring_within_7_days": expiring,
        "median_active_age_days": _days(median),
        "oldest_active_age_days": _days(oldest),
    }


def failing_rules(
    conn: Connection, *, team_id: int | None, since: datetime, until: datetime
) -> dict[int, list[dict[str, Any]]]:
    """Non-pass reasons per team and rule, most frequent first."""
    e = evaluations.c
    reason = func.jsonb_array_elements(evaluations.c.reasons).table_valued(
        sa.column("value", JSONB), joins_implicitly=True
    )
    rule = reason.c.value["rule"].astext
    query = (
        select(
            e.team_id,
            rule.label("rule"),
            func.count().filter(reason.c.value["outcome"].astext == "block").label("blocked"),
            func.count().filter(reason.c.value["outcome"].astext == "warn").label("warned"),
            func.count().filter(reason.c.value["waiver_id"].astext.is_not(None)).label("waived"),
        )
        .select_from(evaluations, reason)
        .where(e.created_at >= since, e.created_at < until)
        .group_by(e.team_id, rule)
        .order_by(e.team_id, func.count().desc(), rule)
    )
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute(_scoped(query, e.team_id, team_id)):
        result[r.team_id].append(
            {"rule": r.rule, "count": r.blocked + r.warned, "block": r.blocked,
             "warn": r.warned, "waived": r.waived}
        )
    return result


def team_rows(conn: Connection, team_id: int | None) -> list[sa.Row]:
    query = select(teams.c.id, teams.c.slug, teams.c.name, teams.c.timezone).order_by(teams.c.slug)
    return list(conn.execute(_scoped(query, teams.c.id, team_id)))


def export_rows(
    conn: Connection,
    *,
    team_id: int | None,
    since: datetime,
    until: datetime,
    service: str | None = None,
    decision: str | None = None,
) -> list[sa.Row]:
    e = evaluations.c
    query = (
        select(
            e.id, e.created_at, teams.c.slug.label("team"), services.c.slug.label("service"),
            e.source, e.pipeline_id, e.commit_sha, e.branch, e.environment, e.version,
            e.decision, policies.c.version.label("policy_version"), e.reasons,
        )
        .select_from(
            evaluations.join(teams, teams.c.id == e.team_id)
            .join(services, services.c.id == e.service_id)
            .outerjoin(policies, policies.c.id == e.policy_id)
        )
        .where(e.created_at >= since, e.created_at < until)
        .order_by(e.created_at, e.id)
    )
    if service is not None:
        query = query.where(services.c.slug == service)
    if decision is not None:
        query = query.where(e.decision == decision)
    return list(conn.execute(_scoped(query, e.team_id, team_id)))


def _days(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)
