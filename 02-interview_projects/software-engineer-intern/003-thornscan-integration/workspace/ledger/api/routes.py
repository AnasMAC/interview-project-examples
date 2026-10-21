"""The ``/api/v1`` endpoints (docs/architecture.md §6).

Ingest upload format: the request body is the raw report file, exactly the
bytes the scanner wrote (no multipart, no JSON wrapper, any Content-Type), with
a mandatory ``Content-Length`` of at most ``Settings.max_upload_bytes``.
Metadata travels in the query string:

* ``repo`` (required): repository name, e.g. ``checkout-api``;
* ``branch`` (required) and ``commit`` (required, 7-40 hex characters);
* ``format`` (optional): ``sarif``, ``kitewatch``, ``depwarden`` or
  ``pentest_csv``; detected from the content when absent;
* ``source`` (optional): the original file name, used in error messages, in
  ``runs.source_name`` and as the tie-break for format detection; ``upload``
  when absent.

Example: ``curl -X POST -H "Authorization: Bearer $LEDGER_ADMIN_TOKEN"
--data-binary @brackish.sarif "http://127.0.0.1:8765/api/v1/ingest?repo=checkout-api&branch=main&commit=4be1f0c9d2&source=brackish.sarif"``.
The whole upload is one transaction: a parse error writes nothing.
"""

from __future__ import annotations

from typing import Any

from ledger import __version__
from ledger.api import findings, teams
from ledger.api.router import Router
from ledger.api.server import Request
from ledger.core import db, migrations, repo
from ledger.core.errors import InvalidInput, NotFound
from ledger.core.log import get_logger
from ledger.core.models import as_dict

log = get_logger("api.routes")
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
_LIST_PARAMS = set(findings.FILTERS) | {"suppressed", "limit", "offset"}

Response = tuple[int, Any]


def health(req: Request) -> Response:
    return 200, {"status": "ok", "version": __version__, "schema_version": migrations.current_version(req.conn)}


def ingest(req: Request) -> Response:
    from ledger.dedupe.ingest import ingest_report

    values = {name: req.one(name) for name in ("repo", "branch", "commit")}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise InvalidInput(f"missing query parameter(s): {', '.join(missing)}", missing=missing)
    source = req.one("source") or "upload"
    if len(source) > 255:
        raise InvalidInput("source must be at most 255 characters")
    repository = repo.repo_by_name(req.conn, values["repo"])
    if repository is None:
        raise NotFound(f"unknown repo {values['repo']!r}", repo=values["repo"])
    data = req.body(req.settings.max_upload_bytes)
    if not data:
        raise InvalidInput("empty request body; send the report file as the body")
    with db.transaction(req.conn):
        result = ingest_report(
            req.conn, req.settings, repo=repository, branch=values["branch"], commit_sha=values["commit"],
            data=data, source=source, fmt=req.one("format") or None,
        )
    log.info("api.ingest", extra={"run_id": result.run_id, "repo": result.repo, "tool": result.tool, "raw": result.raw_count})
    return 201, as_dict(result)


def list_findings(req: Request) -> Response:
    unknown = sorted(set(req.query) - _LIST_PARAMS)
    if unknown:
        raise InvalidInput(f"unknown query parameter(s): {', '.join(unknown)}", parameters=unknown)
    limit = _int(req.one("limit"), "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
    offset = _int(req.one("offset"), "offset", 0, 0, None)
    suppressed = req.one("suppressed") or "false"
    if suppressed not in ("true", "false"):
        raise InvalidInput("suppressed must be true or false", parameter="suppressed")
    filters = {name: req.query.get(name, []) for name in findings.FILTERS}
    items, total = findings.search(req.conn, filters, suppressed=suppressed == "true", limit=limit, offset=offset)
    return 200, {"items": items, "total": total, "limit": limit, "offset": offset}


def finding_detail(req: Request) -> Response:
    return 200, findings.detail(req.conn, req.params["id"])


def triage(req: Request) -> Response:
    body = req.json()
    if not isinstance(body, dict) or not isinstance(body.get("triage"), str):
        raise InvalidInput('body must be a JSON object like {"triage": "confirmed", "note": "..."}')
    assert req.token is not None  # admin route
    with db.transaction(req.conn):
        finding = findings.set_triage(req.conn, req.params["id"], body["triage"], note=body.get("note"), actor=req.token.name)
    return 200, finding


def team_summary(req: Request) -> Response:
    return 200, {"items": teams.summary(req.conn, req.settings)}


def build_router() -> Router:
    router = Router()
    router.add("GET", "/api/v1/health", health, role=None)
    router.add("POST", "/api/v1/ingest", ingest, role="admin")
    router.add("GET", "/api/v1/findings", list_findings, role="read")
    router.add("GET", "/api/v1/findings/{id:int}", finding_detail, role="read")
    router.add("POST", "/api/v1/findings/{id:int}/triage", triage, role="admin")
    router.add("GET", "/api/v1/teams", team_summary, role="read")
    return router


def _int(raw: str | None, name: str, default: int, low: int, high: int | None) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise InvalidInput(f"{name} must be an integer", parameter=name) from None
    if value < low or (high is not None and value > high):
        raise InvalidInput(f"{name} must be at least {low}" + (f" and at most {high}" if high else ""), parameter=name)
    return value
