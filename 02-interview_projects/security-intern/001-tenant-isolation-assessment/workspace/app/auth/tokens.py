"""Bearer API tokens.

A token is ``bpk_`` followed by 40 url-safe characters. The plaintext exists
only in the response that issued it; the database stores the 12 character
prefix (the lookup key), a per-token salt and ``sha256(salt + token)``.

Verification looks the prefix up, hashes the presented token with the stored
salt and compares the digests with :func:`hmac.compare_digest`. Tokens are
revoked by setting ``revoked_at``; a revoked token never authenticates again.
``last_used_at`` is refreshed at most every five minutes to keep the API read
path cheap.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import ensure_utc, now as clock_now
from app.models import ApiToken, Tenant, User

TOKEN_PREFIX = "bpk_"
PREFIX_LENGTH = 12
TOKEN_BYTES = 30
TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class IssuedToken:
    """The one-time plaintext plus the persisted row."""

    plaintext: str
    row: ApiToken


def generate_token() -> str:
    """Return a fresh plaintext token."""
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def token_prefix(token: str) -> str:
    """The 12 character lookup prefix of a token."""
    return token[:PREFIX_LENGTH]


def hash_token(token: str, salt: str) -> str:
    """``sha256(salt + token)``, hex encoded."""
    return hashlib.sha256(f"{salt}{token}".encode()).hexdigest()


def new_salt() -> str:
    """A fresh 32 character hex salt."""
    return secrets.token_hex(16)


def issue_token(session: Session, *, tenant: Tenant, user: User, name: str) -> IssuedToken:
    """Create a token row for ``user``; the caller commits and shows it once."""
    plaintext = generate_token()
    row = ApiToken(
        tenant_id=tenant.id,
        user_id=user.id,
        prefix=token_prefix(plaintext),
        token_hash=hash_token(plaintext, salt := new_salt()),
        salt=salt,
        name=name,
    )
    session.add(row)
    session.flush()
    return IssuedToken(plaintext=plaintext, row=row)


def verify_token(session: Session, token: str | None, *, touch: bool = True) -> ApiToken | None:
    """Return the token row for ``token``, or ``None`` when it is not valid."""
    if not token or len(token) < PREFIX_LENGTH:
        return None
    row = session.scalar(select(ApiToken).where(ApiToken.prefix == token_prefix(token)))
    if row is None or row.revoked_at is not None:
        return None
    if not hmac.compare_digest(hash_token(token, row.salt), row.token_hash):
        return None
    if touch:
        current = clock_now()
        last_used = ensure_utc(row.last_used_at) if row.last_used_at is not None else None
        if last_used is None or current - last_used > TOUCH_INTERVAL:
            row.last_used_at = current
    return row


def revoke_token(session: Session, row: ApiToken) -> None:
    """Revoke a token (idempotent); the caller commits."""
    if row.revoked_at is None:
        row.revoked_at = clock_now()


def parse_bearer(header: str | None) -> str | None:
    """Extract the token from an ``Authorization`` header value."""
    if not header:
        return None
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        return None
    return credentials.strip()
