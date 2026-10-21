"""HTTP routes for waiver requests and reviews.

Teams request waivers with their own key; only security reviewers approve or
reject them. A waiver can be revoked by a reviewer or by the team owning it.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from marshmallow import Schema
from sqlalchemy import select

from gatekeeper.core import auth
from gatekeeper.core.app import current_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import BadRequest, ValidationFailed
from gatekeeper.core.http import load_body, page, page_args
from gatekeeper.core.tables import WAIVER_STATUSES, services
from gatekeeper.waivers import service
from gatekeeper.waivers.schemas import RejectSchema, ReviewSchema, WaiverRequestSchema

bp = Blueprint("waivers", __name__, url_prefix="/v1/waivers")


def _optional_body(schema: Schema) -> dict:
    """Review notes are optional: an empty body counts as ``{}``."""
    return schema.load({}) if not request.get_data() else load_body(schema)


@bp.post("")
@auth.require_role(auth.ROLE_TEAM)
def request_waiver():
    body = load_body(WaiverRequestSchema())
    principal = auth.current_principal()
    with transaction() as conn:
        service_id = None
        if body["service"] is not None:
            service_id = conn.execute(
                select(services.c.id).where(services.c.team_id == principal.team_id,
                                            services.c.slug == body["service"])
            ).scalar()
            if service_id is None:
                raise ValidationFailed(f"unknown service {body['service']!r}",
                                       code="unknown_service")
        view = service.request_waiver(
            conn, team_id=principal.team_id, service_id=service_id, rule=body["rule"],
            version_range=body["version_range"], reason=body["reason"],
            expires_at=body["expires_at"], actor=principal.actor,
            max_days=current_settings().waiver_max_days,
        )
    return jsonify(view), 201


@bp.get("")
def list_waivers():
    limit, offset = page_args()
    status = request.args.get("status")
    if status is not None and status not in WAIVER_STATUSES:
        raise BadRequest(f"status must be one of {', '.join(WAIVER_STATUSES)}")
    with transaction() as conn:
        items, total = service.list_waivers(
            conn, team_id=auth.team_scope(conn, request.args.get("team")), status=status,
            service=request.args.get("service"), rule=request.args.get("rule"),
            limit=limit, offset=offset,
        )
    return jsonify(page(items, total=total, limit=limit, offset=offset))


@bp.get("/<int:waiver_id>")
def get_waiver(waiver_id: int):
    with transaction() as conn:
        auth.ensure_team_access(service.get_row(conn, waiver_id).team_id, f"waiver {waiver_id}")
        return jsonify(service.waiver_view(conn, waiver_id))


@bp.post("/<int:waiver_id>/approve")
@auth.require_role(auth.ROLE_REVIEWER)
def approve_waiver(waiver_id: int):
    body = _optional_body(ReviewSchema())
    with transaction() as conn:
        view = service.approve(conn, waiver_id=waiver_id, actor=auth.current_principal().actor,
                               note=body["note"])
    return jsonify(view)


@bp.post("/<int:waiver_id>/reject")
@auth.require_role(auth.ROLE_REVIEWER)
def reject_waiver(waiver_id: int):
    body = load_body(RejectSchema())
    with transaction() as conn:
        view = service.reject(conn, waiver_id=waiver_id, actor=auth.current_principal().actor,
                              note=body["note"])
    return jsonify(view)


@bp.post("/<int:waiver_id>/revoke")
def revoke_waiver(waiver_id: int):
    body = _optional_body(ReviewSchema())
    with transaction() as conn:
        auth.ensure_team_access(service.get_row(conn, waiver_id).team_id, f"waiver {waiver_id}")
        view = service.revoke(conn, waiver_id=waiver_id, actor=auth.current_principal().actor,
                              note=body["note"])
    return jsonify(view)
