"""HTTP routes for reading the audit log.

``GET /v1/audit?action=&subject_type=&subject_id=&since=&until=`` newest
first. Team keys see their own team's events only; reviewers see every team
(including events without a team) or one with ``?team=``.
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request
from marshmallow import Schema, fields

from gatekeeper.audit import service
from gatekeeper.core import auth
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import BadRequest
from gatekeeper.core.http import page, page_args

bp = Blueprint("audit", __name__, url_prefix="/v1/audit")


class AuditEventSchema(Schema):
    id = fields.Integer()
    team = fields.String(allow_none=True)
    actor = fields.String()
    action = fields.String()
    subject_type = fields.String()
    subject_id = fields.Integer(allow_none=True)
    details = fields.Dict()
    created_at = fields.DateTime()


def query_datetime(name: str) -> datetime | None:
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        # An unencoded "+" in the offset arrives as a space.
        value = datetime.fromisoformat(raw.strip().replace(" ", "+"))
    except ValueError:
        value = None
    if value is None or value.tzinfo is None:
        raise BadRequest(f"{name} must be ISO 8601 with an offset", code="invalid_datetime")
    return value


@bp.get("")
def list_audit_events():
    limit, offset = page_args()
    subject_id = request.args.get("subject_id")
    if subject_id is not None and not subject_id.isdigit():
        raise BadRequest("subject_id must be an integer")
    with transaction() as conn:
        items, total = service.list_events(
            conn,
            team_id=auth.team_scope(conn, request.args.get("team")),
            action=request.args.get("action"),
            subject_type=request.args.get("subject_type"),
            subject_id=int(subject_id) if subject_id is not None else None,
            since=query_datetime("since"),
            until=query_datetime("until"),
            limit=limit,
            offset=offset,
        )
    data = AuditEventSchema(many=True).dump(items)
    return jsonify(page(data, total=total, limit=limit, offset=offset))
