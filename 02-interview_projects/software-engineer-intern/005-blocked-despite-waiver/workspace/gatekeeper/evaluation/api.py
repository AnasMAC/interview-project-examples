"""HTTP routes for policy versions and dry runs.

Team keys act on their own team; security reviewers pick one with
``?team=<slug>`` (required everywhere except the list, where it filters).
"""

from flask import Blueprint, jsonify, request

from gatekeeper.core import auth
from gatekeeper.core.contracts import Submission
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import BadRequest
from gatekeeper.core.http import load_body, page, page_args
from gatekeeper.evaluation import service
from gatekeeper.evaluation.schemas import DryRunResultSchema, DryRunSchema, PublishPolicySchema

bp = Blueprint("policies", __name__, url_prefix="/v1/policies")


def _one_team(conn) -> int:
    team_id = auth.team_scope(conn, request.args.get("team"))
    if team_id is None:
        raise BadRequest("security reviewers must name the team: ?team=<slug>")
    return team_id


@bp.get("")
def list_policies():
    limit, offset = page_args()
    with transaction() as conn:
        team_id = auth.team_scope(conn, request.args.get("team"))
        items, total = service.list_policies(conn, team_id=team_id, limit=limit, offset=offset)
    return jsonify(page(items, total=total, limit=limit, offset=offset))


@bp.post("")
def publish_policy():
    body = load_body(PublishPolicySchema())
    with transaction() as conn:
        view = service.publish_policy(
            conn, team_id=_one_team(conn), source=body["source"],
            actor=auth.current_principal().actor, comment=body["comment"],
        )
    return jsonify(view), 201


@bp.get("/<int:version>")
def get_policy(version: int):
    with transaction() as conn:
        view = service.get_policy(conn, team_id=_one_team(conn), version=version)
    return jsonify(view)


@bp.post("/dry-run")
def dry_run():
    body = load_body(DryRunSchema())
    with transaction() as conn:
        team_id = _one_team(conn)
        service_id = service.service_id_for(conn, team_id=team_id, slug=body["service"])
        submission = Submission(
            source="dry_run", service=body["service"], pipeline_id="dry-run", commit_sha="",
            branch=body["branch"], environment=body["environment"], version=body["version"],
            callback_url=None, evidence=body["evidence"],
        )
        decision = service.dry_run(
            conn, team_id=team_id, service_id=service_id, submission=submission,
            source=body["source"],
        )
    return jsonify(DryRunResultSchema().dump({
        "decision": decision.decision,
        "policy_version": decision.policy_version,
        "draft": body["source"] is not None,
        "reasons": decision.reasons,
        "results": [r.as_reason() for r in decision.results],
    }))
