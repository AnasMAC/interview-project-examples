"""Error model and the JSON error handlers.

Every error response has the same body::

    {"error": {"code": "not_found", "message": "waiver 12 not found", "details": {}}}

Raise one of the ``ApiError`` subclasses from handlers and services; never
build error responses by hand. ``code`` values are part of the API contract
(docs/api.md) and CI pipelines branch on them.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, g, jsonify
from marshmallow import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger("gatekeeper.errors")


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details if details is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class BadRequest(ApiError):
    status, code = 400, "bad_request"


class Unauthorized(ApiError):
    status, code = 401, "unauthorized"


class Forbidden(ApiError):
    status, code = 403, "forbidden"


class NotFound(ApiError):
    status, code = 404, "not_found"


class Conflict(ApiError):
    status, code = 409, "conflict"


class PayloadTooLarge(ApiError):
    status, code = 413, "payload_too_large"


class ValidationFailed(ApiError):
    status, code = 422, "validation_failed"


def _respond(error: ApiError):
    response = jsonify(error.to_dict())
    response.status_code = error.status
    if error.status == 401:
        response.headers["WWW-Authenticate"] = 'Bearer realm="gatekeeper"'
    return response


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(error: ApiError):
        return _respond(error)

    @app.errorhandler(ValidationError)
    def _validation_error(error: ValidationError):
        return _respond(ValidationFailed("request body is invalid", details=error.messages))

    @app.errorhandler(HTTPException)
    def _http_error(error: HTTPException):
        status = error.code or 500
        if status == 413:
            limit = app.config.get("MAX_CONTENT_LENGTH")
            return _respond(PayloadTooLarge(f"request body exceeds {limit} bytes"))
        code = (error.name or "error").lower().replace(" ", "_")
        api_error = ApiError(error.description or error.name, code=code)
        api_error.status = status
        return _respond(api_error)

    @app.errorhandler(Exception)
    def _unhandled(error: Exception):
        log.exception("request.unhandled_error", extra={"request_id": g.get("request_id")})
        api_error = ApiError("internal server error", code="internal_error")
        api_error.status = 500
        return _respond(api_error)
