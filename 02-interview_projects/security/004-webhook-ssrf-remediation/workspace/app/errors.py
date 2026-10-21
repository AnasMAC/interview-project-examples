"""Error types and HTTP error handling.

Handlers answer JSON under ``/api/`` and a small HTML page everywhere else.
Responses never carry stack traces, SQL text or filesystem paths: the detail
goes to the log, the client gets a stable ``code`` and a short message.

Error body shape::

    {"error": {"code": "invalid_transition", "message": "..."}}

Cross-tenant resources are always ``not_found`` (404), never ``forbidden``,
so ids from another tenant cannot be probed.
"""

from __future__ import annotations

import logging

from flask import Flask, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class BellpostError(Exception):
    """Base class for application errors that map onto an HTTP response."""

    status_code = 500
    code = "internal_error"
    message = "internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {"error": {"code": self.code, "message": str(self)}}


class AuthenticationRequired(BellpostError):
    """No session and no usable bearer token."""

    status_code = 401
    code = "unauthenticated"
    message = "authentication required"


class PermissionDenied(BellpostError):
    """The identity is known but the role is not high enough."""

    status_code = 403
    code = "forbidden"
    message = "not allowed"


class CsrfFailed(BellpostError):
    """Missing or mismatched ``csrf_token`` on a state-changing admin request."""

    status_code = 403
    code = "csrf_failed"
    message = "csrf token missing or invalid"


class NotFound(BellpostError):
    """The resource does not exist for this tenant."""

    status_code = 404
    code = "not_found"
    message = "not found"


class Conflict(BellpostError):
    """Generic state conflict (duplicates, already-terminal resources)."""

    status_code = 409
    code = "conflict"
    message = "conflict"


class InvalidTransition(BellpostError):
    """A ticket status change that the state machine does not allow."""

    status_code = 409
    code = "invalid_transition"
    message = "invalid status transition"


class ValidationFailed(BellpostError):
    """A request body or query parameter did not validate."""

    status_code = 422
    code = "validation_failed"
    message = "validation failed"


class FileTooLarge(BellpostError):
    """An upload exceeded ``MAX_FILE_BYTES``."""

    status_code = 413
    code = "file_too_large"
    message = "file too large"


class QuotaExceeded(BellpostError):
    """A ticket's attachment quota was reached."""

    status_code = 413
    code = "quota_exceeded"
    message = "attachment quota exceeded"


class UnsupportedMediaType(BellpostError):
    """The uploaded content type is not on the allowed list."""

    status_code = 415
    code = "unsupported_media_type"
    message = "unsupported content type"


_HTTP_CODES = {
    400: ("bad_request", "the request could not be understood"),
    401: ("unauthenticated", "authentication required"),
    403: ("forbidden", "not allowed"),
    404: ("not_found", "not found"),
    405: ("method_not_allowed", "method not allowed"),
    409: ("conflict", "conflict"),
    413: ("file_too_large", "request too large"),
    415: ("unsupported_media_type", "unsupported content type"),
    429: ("rate_limited", "too many requests"),
}


def wants_json() -> bool:
    """True when the response should be a JSON error body."""
    return request.path.startswith("/api/")


def _html_page(status: int, code: str) -> str:
    title = {
        401: "Sign in required",
        403: "Not allowed",
        404: "Nothing here",
        405: "Method not allowed",
        500: "Something went wrong",
    }.get(status, "Error")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>{code.replace('_', ' ')}</p>"
        '<p><a href="/admin/">Back to the console</a></p>'
        "</body></html>\n"
    )


def register_error_handlers(app: Flask) -> None:
    """Attach the application-wide error handlers to ``app``."""

    @app.errorhandler(BellpostError)
    def _bellpost_error(error: BellpostError):
        if error.status_code >= 500:
            logger.error("application error code=%s", error.code, exc_info=error)
        if wants_json():
            return jsonify(error.to_dict()), error.status_code
        return _html_page(error.status_code, error.code), error.status_code

    @app.errorhandler(HTTPException)
    def _http_error(error: HTTPException):
        code, message = _HTTP_CODES.get(
            error.code or 500, ("internal_error", "internal error")
        )
        if wants_json():
            return jsonify({"error": {"code": code, "message": message}}), error.code
        return _html_page(error.code or 500, code), error.code

    @app.errorhandler(Exception)
    def _unhandled(error: Exception):
        logger.exception("unhandled error: %s", type(error).__name__)
        if current_app.config.get("PROPAGATE_EXCEPTIONS"):
            raise error
        if wants_json():
            return jsonify({"error": {"code": "internal_error", "message": "internal error"}}), 500
        return _html_page(500, "internal_error"), 500
