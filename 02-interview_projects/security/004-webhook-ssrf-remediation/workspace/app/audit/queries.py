"""Reading audit events for the console Activity page.

The Activity page is the one console page that renders UTC (with a visible
``UTC`` label): operators correlate it with server logs, so the tenant
timezone is deliberately not applied here.

Filtering is by action, actor and time range, newest first, keyset paginated on
``(created_at, id)`` like the API lists.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AuditEvent, Tenant


def activity(
    session: Session,
    *,
    tenant: Tenant,
    action: str | None = None,
    actor_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    cursor: str | None = None,
) -> list[AuditEvent]:
    """Newest-first activity rows for the tenant."""
    raise NotImplementedError("app.audit.queries.activity")


def actions_seen(session: Session, *, tenant: Tenant) -> list[str]:
    """The distinct action names the tenant has generated, for the filter menu."""
    raise NotImplementedError("app.audit.queries.actions_seen")
