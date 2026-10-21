"""User and role management (``/admin/users``).

Only admins reach these views (``require_role("admin")``) and only for their
own tenant: the role change form carries the user id, and the user is loaded
with the session's tenant filter, so an agent cannot promote themselves and an
admin cannot touch another tenant's users. Role changes are written to the
audit log as ``user.role_changed``.

Naming note: the console talks about "staff" and "customers" in its copy; the
stored role values are always ``requester``, ``agent`` and ``admin``.
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, User


def list_users(session: Session, tenant: Tenant) -> list[User]:
    """Every user of the tenant, agents and admins first."""
    raise NotImplementedError("app.admin.users.list_users")


def create_user(
    session: Session, *, tenant: Tenant, actor: User, email: str, name: str, role: str
) -> User:
    """Create a user for the tenant (or a pending invitation); 409 on duplicates."""
    raise NotImplementedError("app.admin.users.create_user")


def change_role(session: Session, *, tenant: Tenant, actor: User, user_id: int, role: str) -> User:
    """Change a user's role; the target is loaded with the tenant filter."""
    from app import errors
    if actor.role != "admin":
        raise errors.PermissionDenied("admin role required to change roles")
    target = session.query(User).filter(User.id == user_id, User.tenant_id == tenant.id).first()
    if target is None:
        raise errors.NotFound("user not found")
    target.role = role
    return target


def disable_user(session: Session, *, tenant: Tenant, actor: User, user_id: int) -> User:
    """Disable a user and drop their sessions and tokens."""
    raise NotImplementedError("app.admin.users.disable_user")


def register(bp: Blueprint) -> None:
    """Attach the user routes to the admin blueprint."""
    raise NotImplementedError("app.admin.users.register")
