"""Ticket list, detail, assignment and status changes (``/admin/tickets``).

The console list shows the tenant timezone; the Activity page (``/admin/activity``)
is the only page that renders UTC, with a visible ``UTC`` label. Ticket detail
renders the message trail with Jinja autoescaping on - the email HTML part is
shown as text, never as markup.
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, Ticket, User


def ticket_filters(status: str | None = None, priority: str | None = None) -> dict[str, str]:
    """Validate list filters from the query string."""
    raise NotImplementedError("app.admin.tickets.ticket_filters")


def ticket_list(
    session: Session,
    *,
    tenant: Tenant,
    user: User,
    status: str | None = None,
    priority: str | None = None,
) -> list[Ticket]:
    """Tickets of the tenant, newest first, with requester and assignee loaded."""
    raise NotImplementedError("app.admin.tickets.ticket_list")


def ticket_detail(session: Session, *, tenant: Tenant, ticket_id: int) -> Ticket:
    """One ticket with its messages and attachments; 404 across tenants."""
    raise NotImplementedError("app.admin.tickets.ticket_detail")


def assign(session: Session, *, tenant: Tenant, actor: User, ticket_id: int, assignee_id: int | None) -> Ticket:
    """Assign or unassign; refuses requester accounts as assignees."""
    raise NotImplementedError("app.admin.tickets.assign")


def change_status(session: Session, *, tenant: Tenant, actor: User, ticket_id: int, target: str) -> Ticket:
    """Status change through the shared state machine (409 on invalid)."""
    raise NotImplementedError("app.admin.tickets.change_status")


def register(bp: Blueprint) -> None:
    """Attach the ticket routes to the admin blueprint."""
    raise NotImplementedError("app.admin.tickets.register")
