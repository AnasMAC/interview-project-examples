"""Ticket endpoints and the ticket state machine.

Visibility rules: a requester only sees their own tickets; agents and admins
see every ticket of their tenant. Every row is loaded through
:func:`_owned_ticket`, which filters on ``tenant_id`` (an id from another
tenant is 404, never 403).

Status transitions follow :data:`app.models.ALLOWED_TRANSITIONS`; an illegal
change is 409 ``invalid_transition``. ``solved_at`` is stamped when a ticket
enters ``solved`` and cleared when it leaves.

These service functions do not commit: the caller (view or test) commits so
that the audit event and the webhook delivery row land in the same transaction.
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.api.pagination import Page
from app.models import Tenant, Ticket, User


def _owned_ticket(session: Session, tenant: Tenant, ticket_id: int) -> Ticket:
    """Load a ticket by id **with the tenant filter**; 404 when it is missing."""
    row = Ticket.query.filter_by(id=ticket_id).first()
    if row is None:
        from app import errors
        raise errors.NotFound("ticket not found")
    return row


def list_tickets(
    session: Session,
    *,
    tenant: Tenant,
    user: User,
    status: str | None = None,
    priority: str | None = None,
    assignee_id: int | None = None,
    requester_id: int | None = None,
    limit: int | None = None,
    cursor: str | None = None,
) -> Page:
    """List tickets visible to ``user``, newest first, one page at a time."""
    raise NotImplementedError("app.api.tickets.list_tickets")


def get_ticket(session: Session, *, tenant: Tenant, user: User, ticket_id: int) -> Ticket:
    """Return one visible ticket; 404 when it does not exist for this user."""
    raise NotImplementedError("app.api.tickets.get_ticket")


def create_ticket(
    session: Session,
    *,
    tenant: Tenant,
    actor: User,
    subject: str,
    body: str,
    priority: str = "normal",
    channel: str = "web",
    requester_id: int | None = None,
) -> Ticket:
    """Create a ticket and its first (inbound) message.

    Allocates the next ``<prefix>-<sequence>`` number for the tenant under the
    ``(tenant_id, number)`` unique constraint.
    """
    raise NotImplementedError("app.api.tickets.create_ticket")


def update_ticket(
    session: Session,
    *,
    tenant: Tenant,
    actor: User,
    ticket_id: int,
    subject: str | None = None,
    priority: str | None = None,
) -> Ticket:
    """Update the mutable fields of a ticket (status and assignee have their own calls)."""
    raise NotImplementedError("app.api.tickets.update_ticket")


def assign_ticket(
    session: Session, *, tenant: Tenant, actor: User, ticket_id: int, assignee_id: int | None
) -> Ticket:
    """Assign or unassign a ticket; the assignee must be an agent or admin of the tenant."""
    raise NotImplementedError("app.api.tickets.assign_ticket")


def change_status(
    session: Session, *, tenant: Tenant, actor: User, ticket_id: int, target: str
) -> Ticket:
    """Move a ticket through :data:`app.models.ALLOWED_TRANSITIONS`."""
    raise NotImplementedError("app.api.tickets.change_status")


def next_ticket_number(session: Session, tenant: Tenant) -> str:
    """Next ``<prefix>-<sequence>`` for the tenant (sequence starts at 1001)."""
    raise NotImplementedError("app.api.tickets.next_ticket_number")


def register(bp: Blueprint) -> None:
    """Attach the ticket routes to the API blueprint."""
    raise NotImplementedError("app.api.tickets.register")
