"""Signed-cookie sessions for the admin console.

The cookie (``bellpost_session``) is signed with ``BELLPOST_SECRET_KEY`` and
expires after eight hours. It stores only the user id, the tenant id and a
short fingerprint of the stored password hash - never the role. The role is
re-read from the database on every request, so demoting an agent takes effect
immediately, and a password change invalidates every outstanding cookie
because the fingerprint stops matching.

``login`` clears the session first and re-issues it, which rotates any CSRF
token issued before the login as well. ``logout`` clears the session.
"""

from __future__ import annotations

import hashlib
import hmac

from flask import session as cookie
from sqlalchemy.orm import Session

from app.clock import now as clock_now
from app.errors import AuthenticationRequired
from app.models import Tenant, User

SESSION_COOKIE_NAME = "bellpost_session"
SESSION_LIFETIME_HOURS = 8

_USER_KEY = "uid"
_TENANT_KEY = "tid"
_FINGERPRINT_KEY = "pwf"


def password_fingerprint(password_hash: str) -> str:
    """Short digest of a password hash, stored in the cookie."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def login(session: Session, user: User, *, tenant: Tenant | None = None) -> None:
    """Start a session for ``user``.

    Clears whatever session was there before, stamps ``last_login_at`` and
    issues the new cookie. The caller commits (so the login audit event lands
    in the same transaction).
    """
    if user is None:
        raise AuthenticationRequired("authentication required")
    tenant = tenant or session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise AuthenticationRequired("authentication required")

    cookie.clear()
    cookie.permanent = True
    cookie[_USER_KEY] = user.id
    cookie[_TENANT_KEY] = tenant.id
    cookie[_FINGERPRINT_KEY] = password_fingerprint(user.password_hash)
    user.last_login_at = clock_now()


def logout() -> None:
    """End the current session."""
    cookie.clear()


def load_session_user(session: Session) -> tuple[User, Tenant] | None:
    """Return ``(user, tenant)`` for the cookie, or ``None`` when it is stale.

    Stale means: no cookie, unknown user, disabled user or tenant, or a
    password fingerprint that no longer matches the stored hash.
    """
    user_id = cookie.get(_USER_KEY)
    if not user_id:
        return None
    user = session.get(User, user_id)
    if user is None or user.status != "active":
        return None
    stored = cookie.get(_FINGERPRINT_KEY) or ""
    if not stored or not hmac.compare_digest(stored, password_fingerprint(user.password_hash)):
        cookie.clear()
        return None
    tenant = session.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "active":
        return None
    if cookie.get(_TENANT_KEY) != tenant.id:
        cookie[_TENANT_KEY] = tenant.id
    return user, tenant


def session_user_id() -> int | None:
    """The user id in the current cookie, if any."""
    return cookie.get(_USER_KEY)
