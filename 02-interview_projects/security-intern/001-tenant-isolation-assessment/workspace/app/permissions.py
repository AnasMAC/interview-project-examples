"""Role ranks and tenant ownership checks.

Roles are per tenant and ranked ``requester < agent < admin``. ``require_role``
asks for a minimum rank, so ``require_role("agent")`` admits agents and admins
but not requesters. Unknown role names are a programming error and raise
``ValueError`` early, at import time of the decorated view.

Cross-tenant resources must answer 404: call :func:`require_tenant_match` with
the row you just loaded (or with a tenant id) instead of returning 403, so ids
from another tenant are indistinguishable from ids that do not exist.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from app import tenancy
from app.errors import AuthenticationRequired, NotFound, PermissionDenied
from app.models import User

F = TypeVar("F", bound=Callable)

#: rank per role name; the admin panel and the API both use this ordering.
ROLE_RANKS: dict[str, int] = {"requester": 0, "agent": 1, "admin": 2}


def rank(role: str) -> int:
    """Return the rank of ``role``; unknown names raise ``ValueError``."""
    try:
        return ROLE_RANKS[role]
    except KeyError:
        raise ValueError(f"unknown role {role!r}") from None


def has_role(user: User, *roles: str) -> bool:
    """True when ``user`` holds at least the highest rank in ``roles``."""
    if user is None or user.role not in ROLE_RANKS:
        return False
    minimum = max(rank(role) for role in roles)
    return rank(user.role) >= minimum


def require_role(*roles: str) -> Callable[[F], F]:
    """Decorator: answer 403 unless the current user holds one of ``roles``.

    With no arguments the user must merely be authenticated.
    """
    minimum = max((rank(role) for role in roles), default=0)

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any):
            identity = tenancy.current_identity()
            if identity is None or identity.user is None:
                raise AuthenticationRequired("authentication required")
            if rank(identity.user.role) < minimum:
                raise PermissionDenied("not allowed")
            return view(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def tenant_matches(tenant_id: int | None) -> bool:
    """True when ``tenant_id`` is the current tenant."""
    identity = tenancy.current_identity()
    if identity is None or tenant_id is None:
        return False
    return identity.tenant.id == int(tenant_id)


def require_tenant_match(resource: Any) -> None:
    """Raise 404 unless ``resource`` belongs to the current tenant.

    ``resource`` is a row (anything with ``tenant_id``) or a bare tenant id.
    """
    if resource is None:
        raise NotFound("not found")
    tenant_id = getattr(resource, "tenant_id", resource)
    if not tenant_matches(tenant_id):
        raise NotFound("not found")
