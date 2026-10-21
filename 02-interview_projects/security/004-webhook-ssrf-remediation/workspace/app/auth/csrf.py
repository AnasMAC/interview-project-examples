"""CSRF protection for the admin forms.

Every state-changing admin request (POST, PUT, PATCH, DELETE) must carry the
session-bound token in the ``csrf_token`` field or in the ``X-CSRF-Token``
header. The token is issued on first use and kept in the signed session; it is
never issued while validating, so an empty or unknown token always fails.
Comparison is constant time.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from flask import request, session as cookie

from app.errors import CsrfFailed

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
SESSION_KEY = "csrf"
TOKEN_BYTES = 32
PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

F = TypeVar("F", bound=Callable)


def issue_csrf_token() -> str:
    """Rotate and store a fresh token for this session."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    cookie[SESSION_KEY] = token
    return token


def get_csrf_token() -> str:
    """Return the session token, issuing one if the session has none yet."""
    token = cookie.get(SESSION_KEY)
    if not token:
        token = issue_csrf_token()
    return token


def validate_csrf_token(submitted: str | None) -> bool:
    """True when ``submitted`` matches the token bound to this session."""
    stored = cookie.get(SESSION_KEY)
    if not stored or not submitted:
        return False
    return hmac.compare_digest(stored, submitted)


def submitted_token() -> str | None:
    """The token sent with the current request, if any."""
    return request.form.get(CSRF_FIELD) or request.headers.get(CSRF_HEADER)


def require_csrf(view: F) -> F:
    """Decorator: reject state-changing requests without a valid token."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if request.method in PROTECTED_METHODS and not validate_csrf_token(submitted_token()):
            raise CsrfFailed("csrf token missing or invalid")
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]
