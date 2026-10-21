"""API-key authentication, team scoping and the security-reviewer role.

Keys look like ``gk_demo_`` + 32 ``[a-z0-9]`` characters and are sent as
``Authorization: Bearer <key>``. Only ``sha256(key)`` is stored; the first 16
characters (``prefix``) are kept in clear to find the row, and the hash is
compared in constant time.

Roles:

* ``team``: bound to one team (CI pipelines and team members). Sees and
  changes only its own team's rows; another team's row answers 404, never 403.
* ``security_reviewer``: no team; reads every team, approves or rejects
  waivers and publishes policies for any team.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import current_app, g, request
from sqlalchemy import Connection, insert, select, update

from gatekeeper.core import clock
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import Forbidden, NotFound, Unauthorized
from gatekeeper.core.tables import ROLES, api_keys, teams

KEY_PREFIX = "gk_demo_"
PREFIX_LENGTH = 16
ROLE_TEAM = "team"
ROLE_REVIEWER = "security_reviewer"
_ALPHABET = string.ascii_lowercase + string.digits


@dataclass(frozen=True)
class Principal:
    key_id: int
    name: str
    role: str
    team_id: int | None
    team_slug: str | None

    @property
    def is_reviewer(self) -> bool:
        return self.role == ROLE_REVIEWER

    @property
    def actor(self) -> str:
        """How this caller appears in audit events and ``*_by`` columns."""
        return f"key:{self.name}"


def generate_key() -> str:
    return KEY_PREFIX + "".join(secrets.choice(_ALPHABET) for _ in range(32))


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def issue_key(
    conn: Connection, *, name: str, role: str, team_id: int | None = None, key: str | None = None
) -> tuple[int, str]:
    """Store a new key and return ``(key_id, plaintext)``; the plaintext is not kept."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if (role == ROLE_TEAM) != (team_id is not None):
        raise ValueError("team keys need a team_id, reviewer keys must not have one")
    key = key or generate_key()
    key_id = conn.execute(
        insert(api_keys)
        .values(
            name=name,
            role=role,
            team_id=team_id,
            prefix=key[:PREFIX_LENGTH],
            key_hash=hash_key(key),
            created_at=clock.now(),
        )
        .returning(api_keys.c.id)
    ).scalar_one()
    return key_id, key


def revoke_key(conn: Connection, key_id: int) -> bool:
    result = conn.execute(
        update(api_keys)
        .where(api_keys.c.id == key_id, api_keys.c.revoked_at.is_(None))
        .values(revoked_at=clock.now())
    )
    return result.rowcount == 1


def authenticate(conn: Connection, presented: str) -> Principal | None:
    if not presented.startswith(KEY_PREFIX) or len(presented) < PREFIX_LENGTH:
        return None
    row = conn.execute(
        select(api_keys, teams.c.slug.label("team_slug"))
        .select_from(api_keys.outerjoin(teams, teams.c.id == api_keys.c.team_id))
        .where(api_keys.c.prefix == presented[:PREFIX_LENGTH], api_keys.c.revoked_at.is_(None))
    ).first()
    if row is None or not hmac.compare_digest(row.key_hash, hash_key(presented)):
        return None
    return Principal(row.id, row.name, row.role, row.team_id, row.team_slug)


def public(view: Callable[..., Any]) -> Callable[..., Any]:
    """Mark a view as reachable without a key (health checks only)."""
    view.gatekeeper_public = True  # type: ignore[attr-defined]
    return view


def load_principal() -> None:
    """``before_request`` hook: sets ``g.principal`` or answers 401."""
    view = current_app.view_functions.get(request.endpoint or "")
    if view is None or getattr(view, "gatekeeper_public", False):
        return
    scheme, _, presented = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not presented.strip():
        raise Unauthorized("missing API key", code="missing_api_key")
    with transaction() as conn:
        principal = authenticate(conn, presented.strip())
    if principal is None:
        raise Unauthorized("invalid or revoked API key", code="invalid_api_key")
    g.principal = principal


def current_principal() -> Principal:
    return g.principal


def require_role(*roles: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if current_principal().role not in roles:
                raise Forbidden(f"requires role: {', '.join(roles)}", code="role_required")
            return view(*args, **kwargs)

        return wrapper

    return decorator


def team_scope(conn: Connection, team_slug: str | None) -> int | None:
    """Team id a list endpoint must filter on (``?team=<slug>``).

    Team keys always get their own team; asking for another one is 404.
    Reviewers get the requested team, or ``None`` (all teams) without one.
    """
    principal = current_principal()
    if not principal.is_reviewer:
        if team_slug is not None and team_slug != principal.team_slug:
            raise NotFound(f"team {team_slug!r} not found")
        return principal.team_id
    if team_slug is None:
        return None
    team_id = conn.execute(select(teams.c.id).where(teams.c.slug == team_slug)).scalar()
    if team_id is None:
        raise NotFound(f"team {team_slug!r} not found")
    return team_id


def ensure_team_access(team_id: int, what: str) -> None:
    """404 when a team key touches another team's row (``what``: "waiver 12")."""
    principal = current_principal()
    if not principal.is_reviewer and principal.team_id != team_id:
        raise NotFound(f"{what} not found")
