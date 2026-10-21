"""Tenant resolution and scoping.

Every request resolves at most one :class:`Identity` - from the
``Authorization: Bearer`` header first, then from the signed session cookie -
and stores it on ``flask.g``. The identity is never cached across requests:
the role and the tenant are re-read from the database every time, which is why
a role change or a password change takes effect on the next request.

Rules that the rest of the product relies on:

* a request without credentials reaches the view with ``identity = None``; the
  view (or :func:`require_auth`) turns that into 401 ``unauthenticated``;
* resources are always looked up **with** the tenant filter, so an id from
  another tenant is 404 ``not_found``, never 403;
* ``tenant_scope`` binds a tenant for code that runs outside a request (the
  ingest worker, scripts, tests).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Literal, TypeVar

from flask import Flask, g, has_app_context, has_request_context, request
from sqlalchemy.orm import Session

from app import db
from app.auth import sessions as auth_sessions
from app.auth import tokens as auth_tokens
from app.errors import AuthenticationRequired, NotFound
from app.models import ApiToken, Tenant, User

F = TypeVar("F", bound=Callable)


@dataclass(frozen=True)
class Identity:
    """Who the current request is: tenant, user and how they authenticated."""

    tenant: Tenant
    user: User | None
    api_token: ApiToken | None
    source: Literal["session", "token"]


def init_app(app: Flask) -> None:
    """Resolve the identity before every request; sessions close in db.init_app."""

    @app.before_request
    def _resolve() -> None:
        g.identity = resolve_identity(db.get_session())


def _authorization_header() -> str | None:
    if not has_request_context():
        return None
    return request.headers.get("Authorization")


def resolve_identity(session: Session) -> Identity | None:
    """Return the identity carried by the request, or ``None``."""
    token = auth_tokens.parse_bearer(_authorization_header())
    if token is not None:
        row = auth_tokens.verify_token(session, token)
        if row is None:
            return None
        # Persist the last_used_at touch (if any) for the request ahead.
        session.commit()
        user = session.get(User, row.user_id)
        tenant = session.get(Tenant, row.tenant_id)
        if user is None or tenant is None:
            return None
        if user.status != "active" or tenant.status != "active":
            return None
        return Identity(tenant=tenant, user=user, api_token=row, source="token")
    if has_request_context():
        loaded = auth_sessions.load_session_user(session)
        if loaded is not None:
            user, tenant = loaded
            return Identity(tenant=tenant, user=user, api_token=None, source="session")
    return None


def current_identity() -> Identity | None:
    """Return the identity of the current request, or ``None``."""
    if not has_app_context():
        return None
    return getattr(g, "identity", None)


def current_tenant() -> Tenant:
    """Return the current tenant; 401 when the request is anonymous."""
    identity = current_identity()
    if identity is None:
        raise AuthenticationRequired("authentication required")
    return identity.tenant


def current_user() -> User:
    """Return the current user; 401 when the request is anonymous."""
    identity = current_identity()
    if identity is None or identity.user is None:
        raise AuthenticationRequired("authentication required")
    return identity.user


def set_identity(identity: Identity | None) -> None:
    """Bind an identity directly (tests, impersonation helpers)."""
    g.identity = identity


def require_auth(view: F) -> F:
    """Decorator: answer 401 unless the request carries valid credentials."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_identity() is None:
            raise AuthenticationRequired("authentication required")
        return view(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


@contextmanager
def tenant_scope(tenant: Tenant | int, *, user: User | None = None) -> Iterator[Tenant]:
    """Bind ``tenant`` for code that calls :func:`current_tenant`.

    Requires a Flask application context::

        with app.app_context(), tenant_scope(tenant):
            ...
    """
    session = db.get_session()
    if isinstance(tenant, int):
        loaded = session.get(Tenant, tenant)
        if loaded is None:
            raise NotFound("tenant not found")
        tenant = loaded
    previous = getattr(g, "identity", None)
    g.identity = Identity(tenant=tenant, user=user, api_token=None, source="session")
    try:
        yield tenant
    finally:
        g.identity = previous
