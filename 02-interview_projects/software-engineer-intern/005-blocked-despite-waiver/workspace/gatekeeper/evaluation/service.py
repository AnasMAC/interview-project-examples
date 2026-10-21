"""Evaluation entry points (docs/architecture.md, "Request flow").

``evaluate`` and ``dry_run`` only read; the caller (ingest) stores the
decision. ``publish_policy`` inserts a new version and its audit event in the
caller's transaction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Row, func, insert, select

from gatekeeper.core import clock
from gatekeeper.core.contracts import Decision, Submission
from gatekeeper.core.errors import NotFound, ValidationFailed
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import policies, services, teams
from gatekeeper.evaluation import compiler, evaluator
from gatekeeper.evaluation.compiler import CompiledPolicy
from gatekeeper.evaluation.schemas import PolicySchema

log = get_logger(__name__)

_view = PolicySchema()
_list_view = PolicySchema(exclude=("source",))


def active_policy(conn: Connection, team_id: int) -> Row | None:
    """The team's highest policy version, or ``None`` when it never published one."""
    return conn.execute(
        select(policies)
        .where(policies.c.team_id == team_id)
        .order_by(policies.c.version.desc())
        .limit(1)
    ).first()


def evaluate(
    conn: Connection, *, team_id: int, service_id: int, submission: Submission
) -> Decision:
    row = active_policy(conn, team_id)
    compiled = compiler.compiled_for(row) if row is not None else None
    return _decide(conn, compiled, team_id=team_id, service_id=service_id, submission=submission)


def dry_run(
    conn: Connection, *, team_id: int, service_id: int, submission: Submission,
    source: str | None = None,
) -> Decision:
    """What ``evaluate`` would answer, against the active policy or a draft ``source``.

    Waivers are applied as for a real evaluation; nothing is written and a
    draft is neither stored nor cached.
    """
    if source is None:
        return evaluate(conn, team_id=team_id, service_id=service_id, submission=submission)
    compiled = compiler.compile_source(source, team_id=team_id)
    return _decide(conn, compiled, team_id=team_id, service_id=service_id, submission=submission)


def _decide(
    conn: Connection, compiled: CompiledPolicy | None, *, team_id: int, service_id: int,
    submission: Submission,
) -> Decision:
    if compiled is None:
        return Decision("warn", [evaluator.MISSING_POLICY], None, None)
    results = evaluator.run_rules(compiled, submission)
    if any(r.outcome != "pass" for r in results):
        # Imported here: the waivers package imports evaluation.rules for rule ids.
        from gatekeeper.waivers.service import apply_waivers

        results = apply_waivers(
            conn, team_id=team_id, service_id=service_id, version=submission.version,
            results=results,
        )
    return Decision(evaluator.aggregate(results), results, compiled.policy_id, compiled.version)


def publish_policy(
    conn: Connection, *, team_id: int, source: str, actor: str, comment: str | None = None
) -> dict[str, Any]:
    """Validate ``source`` and store it as the team's next version (the new active policy)."""
    compiled = compiler.compile_source(source)
    team = conn.execute(
        select(teams.c.id, teams.c.slug).where(teams.c.id == team_id).with_for_update()
    ).first()  # the row lock serializes concurrent publishes of one team
    if team is None:
        raise NotFound(f"team {team_id} not found")
    current = conn.execute(
        select(func.max(policies.c.version)).where(policies.c.team_id == team_id)
    ).scalar()
    version = (current or 0) + 1
    row = conn.execute(
        insert(policies)
        .values(team_id=team_id, version=version, source=source, comment=comment,
                created_by=actor, created_at=clock.now())
        .returning(policies)
    ).one()

    from gatekeeper.audit.service import record

    record(conn, action="policy.published", actor=actor, subject_type="policy",
           subject_id=row.id, team_id=team_id, details={"version": version, "comment": comment})
    compiler.invalidate_team(team_id)
    log.info("evaluation.policy_published",
             extra={"team_id": team_id, "policy_id": row.id, "version": version})
    return _view.dump({**row._asdict(), "team": team.slug, "active": True,
                       "warnings": list(compiled.warnings)})


def _policy_rows():
    latest = func.max(policies.c.version).over(partition_by=policies.c.team_id)
    return select(
        policies, teams.c.slug.label("team"), (policies.c.version == latest).label("active")
    ).join(teams, teams.c.id == policies.c.team_id)


def get_policy(conn: Connection, *, team_id: int, version: int) -> dict[str, Any]:
    rows = _policy_rows().where(policies.c.team_id == team_id).subquery()
    row = conn.execute(select(rows).where(rows.c.version == version)).first()
    if row is None:
        raise NotFound(f"policy version {version} not found")
    return _view.dump(row._asdict())


def list_policies(
    conn: Connection, *, team_id: int | None, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """Policy versions, newest first; ``team_id`` None lists every team (reviewers)."""
    query = _policy_rows()
    total = select(func.count()).select_from(policies)
    if team_id is not None:
        query = query.where(policies.c.team_id == team_id)
        total = total.where(policies.c.team_id == team_id)
    query = query.order_by(policies.c.created_at.desc(), policies.c.id.desc())
    rows = conn.execute(query.limit(limit).offset(offset)).all()
    return [_list_view.dump(r._asdict()) for r in rows], conn.execute(total).scalar_one()


def service_id_for(conn: Connection, *, team_id: int, slug: str) -> int:
    service_id = conn.execute(
        select(services.c.id).where(services.c.team_id == team_id, services.c.slug == slug)
    ).scalar()
    if service_id is None:
        raise ValidationFailed(f"unknown service {slug!r}", code="unknown_service")
    return service_id
