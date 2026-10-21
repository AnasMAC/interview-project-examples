"""One error body for the whole API.

Every error response is ``{"error": {"code", "message", "details"}}``.
Objects of another org are reported exactly like missing ones (404).
"""

from __future__ import annotations

import math

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.views import exception_handler

from atlas.core.normalize import NormalizationError


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


_CODES = {
    exceptions.ValidationError: "validation_failed",
    exceptions.ParseError: "parse_error",
    exceptions.NotAuthenticated: "unauthenticated",
    exceptions.AuthenticationFailed: "unauthenticated",
    exceptions.PermissionDenied: "forbidden",
    exceptions.NotFound: "not_found",
    exceptions.MethodNotAllowed: "method_not_allowed",
    exceptions.UnsupportedMediaType: "unsupported_media_type",
    exceptions.Throttled: "throttled",
    Conflict: "conflict",
}


def _translate(exc: Exception) -> Exception:
    if isinstance(exc, Http404 | ObjectDoesNotExist):
        return exceptions.NotFound()
    if isinstance(exc, DjangoPermissionDenied):
        return exceptions.PermissionDenied()
    if isinstance(exc, DjangoValidationError):
        return exceptions.ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    if isinstance(exc, NormalizationError):
        return exceptions.ValidationError({"detail": [str(exc)]})
    return exc


def api_exception_handler(exc, context):
    exc = _translate(exc)
    response = exception_handler(exc, context)
    if response is None:
        return None  # unexpected error: Django's 500 handling and logging
    code = next((c for cls, c in _CODES.items() if isinstance(exc, cls)), None)
    if code is None:
        code = getattr(exc, "default_code", "error")
    if isinstance(exc, exceptions.ValidationError):
        message, details = "Invalid request.", response.data
    else:
        message, details = str(getattr(exc, "detail", exc)), None
    if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
        details = {"retry_after_seconds": math.ceil(exc.wait)}
    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
