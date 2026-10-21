"""Storing a CI submission: idempotency, evaluation, evidence, audit, callback.

``submit`` runs in the caller's transaction and never commits: the decision, its
evidence, audit events and outbox row are written together or not at all."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from psycopg.errors import UniqueViolation
from sqlalchemy import Connection, Row, Select, func, insert, select
from sqlalchemy.exc import IntegrityError

from gatekeeper.core import clock
from gatekeeper.core.auth import Principal
from gatekeeper.core.contracts import Decision, Submission
from gatekeeper.core.errors import NotFound, ValidationFailed
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import evaluations, evidence, policies, services, teams
from gatekeeper.ingest import idempotency
from gatekeeper.ingest.schemas import EvaluationViewSchema

log = get_logger(__name__)

IDEMPOTENCY_INDEX = "uq_evaluations_team_id_idempotency_key"
_view_schema = EvaluationViewSchema()


def _view_query() -> Select:
    return select(
        evaluations,
        teams.c.slug.label("team"),
        services.c.slug.label("service"),
        policies.c.version.label("policy_version"),
    ).select_from(
        evaluations.join(teams, teams.c.id == evaluations.c.team_id)
        .join(services, services.c.id == evaluations.c.service_id)
        .outerjoin(policies, policies.c.id == evaluations.c.policy_id)
    )


def _to_view(row: Row) -> dict[str, Any]:
    data = row._asdict()
    data["created_at"] = row.created_at.astimezone(UTC).isoformat(timespec="seconds")
    return _view_schema.dump(data)


def evaluation_view(conn: Connection, evaluation_id: int) -> dict[str, Any]:
    row = conn.execute(_view_query().where(evaluations.c.id == evaluation_id)).first()
    if row is None:
        raise NotFound(f"evaluation {evaluation_id} not found")
    return _to_view(row)


def list_evaluations(
    conn: Connection, *, team_id: int | None, service: str | None = None,
    decision: str | None = None, branch: str | None = None, limit: int, offset: int,
) -> tuple[list[dict[str, Any]], int]:
    """Newest first; ``team_id`` None means every team (reviewers)."""
    filters = [(evaluations.c.team_id, team_id), (services.c.slug, service),
               (evaluations.c.decision, decision), (evaluations.c.branch, branch)]
    conditions = [column == value for column, value in filters if value is not None]
    total = conn.execute(
        select(func.count())
        .select_from(evaluations.join(services, services.c.id == evaluations.c.service_id))
        .where(*conditions)
    ).scalar_one()
    rows = conn.execute(
        _view_query()
        .where(*conditions)
        .order_by(evaluations.c.created_at.desc(), evaluations.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_to_view(row) for row in rows], total


def _service_id(conn: Connection, team_id: int, slug: str) -> int:
    service_id = conn.execute(
        select(services.c.id).where(services.c.team_id == team_id, services.c.slug == slug)
    ).scalar()
    if service_id is None:
        raise ValidationFailed(
            f"service {slug!r} is not registered for this team",
            code="unknown_service",
            details={"service": slug},
        )
    return service_id


def _is_idempotency_race(exc: IntegrityError) -> bool:
    orig = exc.orig
    return isinstance(orig, UniqueViolation) and orig.diag.constraint_name == IDEMPOTENCY_INDEX


def _record_audit(conn: Connection, principal: Principal, evaluation_id: int,
                  decision: Decision) -> None:
    from gatekeeper.audit.service import record

    violated = [r for r in decision.results if r.outcome != "pass"]
    waived = [r for r in violated if r.waiver_id is not None]
    who = {"actor": principal.actor, "team_id": principal.team_id}
    record(conn, action="evaluation.decided", subject_type="evaluation",
           subject_id=evaluation_id, **who, details={
               "decision": decision.decision, "policy_version": decision.policy_version,
               "rules": [r.rule for r in violated], "waiver_ids": [r.waiver_id for r in waived]})
    for result in waived:
        record(conn, action="waiver.applied", subject_type="waiver", subject_id=result.waiver_id,
               **who, details={"evaluation_id": evaluation_id, "rule": result.rule})


def submit(
    conn: Connection, *, principal: Principal, submission: Submission,
    idempotency_key: str | None, payload_sha256: str,
) -> tuple[dict[str, Any], bool]:
    """Evaluate and store one submission; ``(view, created)``, created False on replay."""
    from gatekeeper.callbacks.service import enqueue
    from gatekeeper.evaluation.service import evaluate

    team_id = principal.team_id
    if idempotency_key is not None:
        replayed = idempotency.find_replay(
            conn, team_id=team_id, key=idempotency_key, payload_sha256=payload_sha256
        )
        if replayed is not None:
            log.info("ingest.idempotent_replay", extra={"evaluation_id": replayed})
            return evaluation_view(conn, replayed), False

    service_id = _service_id(conn, team_id, submission.service)
    decision = evaluate(conn, team_id=team_id, service_id=service_id, submission=submission)
    copied = ("source", "pipeline_id", "commit_sha", "branch", "environment", "version",
              "callback_url")
    values = {name: getattr(submission, name) for name in copied} | {
        "team_id": team_id, "service_id": service_id, "policy_id": decision.policy_id,
        "decision": decision.decision, "reasons": decision.reasons,
        "idempotency_key": idempotency_key, "payload_sha256": payload_sha256,
        "created_at": clock.now(),
    }
    try:
        with conn.begin_nested():
            evaluation_id = conn.execute(
                insert(evaluations).values(**values).returning(evaluations.c.id)
            ).scalar_one()
    except IntegrityError as exc:
        # A concurrent request with the same key committed first: answer as its replay.
        if idempotency_key is None or not _is_idempotency_race(exc):
            raise
        replayed = idempotency.find_replay(
            conn, team_id=team_id, key=idempotency_key, payload_sha256=payload_sha256
        )
        if replayed is None:
            raise
        log.info("ingest.idempotent_race", extra={"evaluation_id": replayed})
        return evaluation_view(conn, replayed), False

    if submission.evidence:
        rows = [{"evaluation_id": evaluation_id, "kind": kind, "data": data}
                for kind, data in submission.evidence.items()]
        conn.execute(insert(evidence), rows)
    _record_audit(conn, principal, evaluation_id, decision)
    view = evaluation_view(conn, evaluation_id)
    if submission.callback_url:
        enqueue(conn, team_id=team_id, event="evaluation.decided", url=submission.callback_url,
                payload={"event": "evaluation.decided", "evaluation": view},
                evaluation_id=evaluation_id)
    log.info("ingest.evaluation_decided", extra={
        "evaluation_id": evaluation_id, "team_id": team_id, "decision": decision.decision})
    return view, True
