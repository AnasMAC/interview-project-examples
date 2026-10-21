"""HTTP routes for scorecards and CSV export.

Both routes take ``?days=`` (the window ending at ``?until=``, default now)
and ``?team=`` (reviewers only; team keys always get their own team).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from gatekeeper.core import auth, clock
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import BadRequest
from gatekeeper.core.tables import DECISIONS
from gatekeeper.reporting import export, queries

bp = Blueprint("reports", __name__, url_prefix="/v1/reports")

DEFAULT_DAYS = 28
MAX_DAYS = 366
TOP_RULES = 5


def _window() -> tuple[datetime, datetime, int]:
    try:
        days = int(request.args.get("days", DEFAULT_DAYS))
    except ValueError as exc:
        raise BadRequest("days must be an integer") from exc
    if not 1 <= days <= MAX_DAYS:
        raise BadRequest(f"days must be 1..{MAX_DAYS}")
    raw = request.args.get("until")
    if raw is None:
        until = clock.now()
    else:
        try:
            until = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise BadRequest("until must be ISO 8601", code="invalid_datetime") from exc
        if until.tzinfo is None:
            raise BadRequest("until needs a UTC offset", code="invalid_datetime")
    return until - timedelta(days=days), until, days


def _rate(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


@bp.get("/scorecard")
def scorecard():
    since, until, days = _window()
    with transaction() as conn:
        team_id = auth.team_scope(conn, request.args.get("team"))
        window = {"team_id": team_id, "since": since, "until": until}
        counts = queries.decision_counts(conn, **window)
        waiver_stats = queries.waiver_stats(conn, **window)
        rules = queries.failing_rules(conn, **window)
        team_rows = queries.team_rows(conn, team_id)
    empty_waivers = queries.empty_waiver_stats()
    cards = []
    for team in team_rows:
        c = counts.get(team.id, {"total": 0, "block": 0, "warn": 0})
        cards.append({
            "team": team.slug,
            "name": team.name,
            "timezone": team.timezone,
            "evaluations": c["total"],
            "decisions": {"pass": c["total"] - c["block"] - c["warn"], "warn": c["warn"],
                          "block": c["block"]},
            "block_rate": _rate(c["block"], c["total"]),
            "warn_rate": _rate(c["warn"], c["total"]),
            "waivers": waiver_stats.get(team.id, empty_waivers),
            "top_failing_rules": rules.get(team.id, [])[:TOP_RULES],
        })
    return jsonify({
        "window": {"since": since.isoformat(), "until": until.isoformat(), "days": days},
        "generated_at": clock.now().isoformat(),
        "teams": cards,
    })


@bp.get("/export.csv")
def export_csv():
    since, until, _ = _window()
    decision = request.args.get("decision")
    if decision is not None and decision not in DECISIONS:
        raise BadRequest(f"decision must be one of {', '.join(DECISIONS)}")
    with transaction() as conn:
        team_id = auth.team_scope(conn, request.args.get("team"))
        rows = queries.export_rows(
            conn, team_id=team_id, since=since, until=until,
            service=request.args.get("service"), decision=decision,
        )
    filename = f"evaluations-{since:%Y%m%d}-{until:%Y%m%d}.csv"
    return Response(
        export.render_csv(rows),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
