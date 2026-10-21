"""Bearer token authentication with two roles: ``read`` (GET endpoints) and ``admin`` (everything)."""

from __future__ import annotations

import hmac
from collections.abc import Iterable

from ledger.core.config import ApiToken
from ledger.core.errors import Forbidden, Unauthorized

ROLE_RANK = {"read": 1, "admin": 2}


def authenticate(header: str | None, tokens: Iterable[ApiToken]) -> ApiToken:
    """The configured token presented in an ``Authorization: Bearer <token>`` header.

    Every configured token is compared in constant time, and the loop never
    stops early, so response timing does not reveal how much of a token or
    which token matched.
    """
    scheme, _, presented = (header or "").strip().partition(" ")
    presented = presented.strip()
    if scheme.lower() != "bearer" or not presented:
        raise Unauthorized("missing bearer token")
    candidate = presented.encode("utf-8")
    match = None
    for token in tokens:
        if hmac.compare_digest(candidate, token.token.encode("utf-8")) and match is None:
            match = token
    if match is None:
        raise Unauthorized("unknown token")
    return match


def require(token: ApiToken, role: str) -> None:
    if ROLE_RANK.get(token.role, 0) < ROLE_RANK[role]:
        raise Forbidden(f"this endpoint needs the {role} role", role=role)
