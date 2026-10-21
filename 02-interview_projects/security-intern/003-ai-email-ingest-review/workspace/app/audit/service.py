"""Writing audit events.

``record`` adds a row to the **caller's** session and returns it - it never
opens its own transaction, so an event and the change it describes land
together: a rolled-back request leaves no audit trail and a committed one
always has its trail. ``detail`` is redacted before it is stored (tokens,
``DEMO-`` values, password fields) and should stay small: ids, before/after
values, never request bodies.

The action names come from :data:`app.models.AUDIT_ACTIONS`.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent, Tenant, User


def record(
    session: Session,
    *,
    tenant: Tenant,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the caller's transaction."""
    raise NotImplementedError("app.audit.service.record")
