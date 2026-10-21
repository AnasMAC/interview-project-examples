"""Bellpost - the multi-tenant helpdesk platform built by Glasswick.

``create_app`` is the only supported entry point::

    flask --app app:create_app run
    gunicorn "app:create_app()" --bind 127.0.0.1:8080

The factory wires configuration, the database session lifecycle, tenant
resolution, structured logging, the error handlers and the two blueprints
(``/api/v1`` for the ticket API, ``/admin`` for the agent console).
"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta

from flask import Flask, Response, g, jsonify, request

from app import db, tenancy
from app.admin import create_admin_blueprint
from app.api import create_api_blueprint
from app.auth import csrf, sessions
from app.config import Settings, get_settings, set_settings
from app.errors import register_error_handlers
from app.logging import configure_logging, get_logger

__version__ = "1.4.2"

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> Flask:
    """Build the Flask application.

    Passing ``settings`` installs them for the whole process (used by tests and
    scripts); otherwise the environment is read through
    :func:`app.config.get_settings`.
    """
    if settings is not None:
        set_settings(settings)
    settings = get_settings()
    configure_logging()

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_NAME=sessions.SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.is_production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=sessions.SESSION_LIFETIME_HOURS),
        TESTING=settings.is_test,
        PROPAGATE_EXCEPTIONS=settings.is_test,
    )
    if settings.is_production and settings.uses_demo_secret:
        logger.warning("BELLPOST_SECRET_KEY still holds a demo value while running in production")

    db.init_app(app)
    tenancy.init_app(app)
    register_error_handlers(app)

    app.jinja_env.globals["csrf_token"] = csrf.get_csrf_token
    app.jinja_env.globals["app_version"] = __version__

    _register_request_logging(app)
    _register_health(app)
    app.register_blueprint(create_api_blueprint())
    app.register_blueprint(create_admin_blueprint())

    logger.info("app.created", extra={"env": settings.env, "app_version": __version__})
    return app


def _register_request_logging(app: Flask) -> None:
    """One structured line per request, with the request id echoed back."""

    @app.before_request
    def _start_request() -> None:
        g.request_id = uuid.uuid4().hex[:12]
        g.request_started = time.perf_counter()

    @app.after_request
    def _log_request(response: Response) -> Response:
        started = getattr(g, "request_started", None)
        identity = tenancy.current_identity()
        logger.info(
            "http.request",
            extra={
                "request_id": getattr(g, "request_id", None),
                "http_method": request.method,
                "http_path": request.path,
                "http_status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2)
                if started is not None
                else None,
                "tenant_id": identity.tenant.id if identity is not None else None,
                "user_id": identity.user.id if identity is not None and identity.user else None,
            },
        )
        response.headers.setdefault("X-Request-Id", str(getattr(g, "request_id", "")))
        return response


def _register_health(app: Flask) -> None:
    @app.get("/healthz")
    def healthz():
        """Liveness for the load balancer: it checks the database only."""
        database_ok = db.check_database()
        payload = {
            "status": "ok" if database_ok else "degraded",
            "database": "ok" if database_ok else "error",
            "version": __version__,
        }
        return jsonify(payload), 200 if database_ok else 503

    @app.get("/")
    def index() -> Response:
        body = (
            f"Bellpost {__version__}\n"
            "  API      /api/v1\n"
            "  console  /admin\n"
            "  health   /healthz\n"
        )
        return Response(body, mimetype="text/plain")
