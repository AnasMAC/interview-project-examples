"""HTTP routes of the evidence API."""

from __future__ import annotations

import json

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from gatekeeper.core import auth
from gatekeeper.core.app import current_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import BadRequest, NotFound, PayloadTooLarge
from gatekeeper.core.http import page, page_args
from gatekeeper.core.tables import DECISIONS, evaluations
from gatekeeper.ingest import idempotency, service
from gatekeeper.ingest.adapters import to_submission

bp = Blueprint("ingest", __name__, url_prefix="/v1/evaluations")


def _read_payload() -> dict:
    limit = current_settings().max_payload_bytes
    too_large = PayloadTooLarge(f"request body exceeds {limit} bytes")
    if (request.content_length or 0) > limit:
        raise too_large
    raw = request.get_data(cache=False)
    if len(raw) > limit:
        raise too_large
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise BadRequest("request body must be a JSON document", code="invalid_json") from exc
    if not isinstance(payload, dict):
        raise BadRequest("request body must be a JSON object", code="invalid_json")
    return payload


@bp.post("")
@auth.require_role(auth.ROLE_TEAM)
def create_evaluation():
    key = idempotency.parse_key(request.headers.get(idempotency.HEADER))
    payload = _read_payload()
    submission = to_submission(payload)
    with transaction() as conn:
        view, created = service.submit(
            conn, principal=auth.current_principal(), submission=submission,
            idempotency_key=key, payload_sha256=idempotency.payload_sha256(payload),
        )
    response = jsonify(view)
    response.headers["Location"] = f"/v1/evaluations/{view['id']}"
    if created:
        response.status_code = 201
    else:
        response.headers[idempotency.REPLAY_HEADER] = "true"
    return response


@bp.get("")
def list_evaluations():
    limit, offset = page_args()
    decision = request.args.get("decision")
    if decision is not None and decision not in DECISIONS:
        raise BadRequest(f"decision must be one of: {', '.join(DECISIONS)}")
    with transaction() as conn:
        items, total = service.list_evaluations(
            conn, team_id=auth.team_scope(conn, request.args.get("team")),
            service=request.args.get("service"), decision=decision,
            branch=request.args.get("branch"), limit=limit, offset=offset,
        )
    return jsonify(page(items, total=total, limit=limit, offset=offset))


@bp.get("/<int:evaluation_id>")
def get_evaluation(evaluation_id: int):
    with transaction() as conn:
        team_id = conn.execute(
            select(evaluations.c.team_id).where(evaluations.c.id == evaluation_id)
        ).scalar()
        if team_id is None:
            raise NotFound(f"evaluation {evaluation_id} not found")
        auth.ensure_team_access(team_id, f"evaluation {evaluation_id}")
        view = service.evaluation_view(conn, evaluation_id)
    return jsonify(view)
