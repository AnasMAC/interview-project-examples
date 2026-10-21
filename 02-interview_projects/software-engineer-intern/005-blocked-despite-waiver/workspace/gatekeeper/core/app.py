"""Application factory.

Blueprints are listed by import path so a component is wired by adding one
line here. Every request gets a request id (``X-Request-Id``, echoed back),
an authenticated ``g.principal`` (see ``auth.load_principal``) and one
``request.completed`` log line.
"""

from __future__ import annotations

import importlib
import re
import time
import uuid

from flask import Blueprint, Flask, current_app, g, jsonify, request
from sqlalchemy import text

from gatekeeper import __version__
from gatekeeper.core import auth
from gatekeeper.core.config import Settings, get_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import register_error_handlers
from gatekeeper.core.logging import configure_logging, get_logger

BLUEPRINTS = (
    "gatekeeper.ingest.api:bp",
    "gatekeeper.evaluation.api:bp",
    "gatekeeper.waivers.api:bp",
    "gatekeeper.audit.api:bp",
    "gatekeeper.reporting.api:bp",
)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = get_logger("gatekeeper.http")
core_bp = Blueprint("core", __name__)


@core_bp.get("/healthz")
@auth.public
def healthz():
    try:
        with transaction() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure means degraded
        log.warning("health.db_unreachable", exc_info=True)
        return jsonify({"status": "degraded", "version": __version__}), 503
    return jsonify({"status": "ok", "version": __version__})


@core_bp.get("/v1/whoami")
def whoami():
    p = auth.current_principal()
    return jsonify({"key": p.name, "role": p.role, "team": p.team_slug})


def current_settings() -> Settings:
    """Settings of the running app (tests may pass their own to ``create_app``)."""
    return current_app.config["GATEKEEPER_SETTINGS"]


def _import_blueprint(path: str) -> Blueprint:
    module_name, _, attr = path.partition(":")
    return getattr(importlib.import_module(module_name), attr)


def _start_request() -> None:
    incoming = request.headers.get("X-Request-Id", "")
    g.request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
    g.started = time.perf_counter()


def _finish_request(response):
    response.headers["X-Request-Id"] = g.get("request_id", "")
    principal = g.get("principal")
    elapsed_ms = (time.perf_counter() - g.get("started", time.perf_counter())) * 1000
    log.info(
        "request.completed",
        extra={
            "request_id": g.get("request_id"),
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round(elapsed_ms, 1),
            "key": principal.name if principal else None,
            "team_id": principal.team_id if principal else None,
        },
    )
    return response


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format, settings.service_name)
    app = Flask("gatekeeper")
    app.config.update(
        GATEKEEPER_SETTINGS=settings,
        MAX_CONTENT_LENGTH=settings.max_payload_bytes,
        TESTING=settings.env == "test",
    )
    app.json.sort_keys = False
    register_error_handlers(app)
    app.before_request(_start_request)
    app.before_request(auth.load_principal)
    app.after_request(_finish_request)
    app.register_blueprint(core_bp)
    for path in BLUEPRINTS:
        app.register_blueprint(_import_blueprint(path))
    return app
