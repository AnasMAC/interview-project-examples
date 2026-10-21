"""Ticket message list and reply.

``GET  /api/v1/tickets/<id>/messages`` lists the conversation oldest first.
``POST /api/v1/tickets/<id>/messages`` appends a reply (``direction`` is
``outbound`` for agents and admins, ``inbound`` for the requester writing back)
and publishes ``message.created``.

Both endpoints go through the ticket visibility check in
:mod:`app.api.tickets`, so a requester can only read and write their own
tickets.
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Message, Tenant, Ticket, User


def list_messages(session: Session, *, tenant: Tenant, user: User, ticket: Ticket) -> list[Message]:
    """Every message of a visible ticket, oldest first."""
    raise NotImplementedError("app.api.messages.list_messages")


def create_reply(
    session: Session,
    *,
    tenant: Tenant,
    author: User,
    ticket: Ticket,
    body: str,
    direction: str = "outbound",
) -> Message:
    """Append a reply to ``ticket`` and record the audit event and webhook."""
    raise NotImplementedError("app.api.messages.create_reply")


def register(bp: Blueprint) -> None:
    """Attach the message routes to the API blueprint."""
    raise NotImplementedError("app.api.messages.register")
