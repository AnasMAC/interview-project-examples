"""JSON shapes returned by the ticket API.

Timestamps are ISO 8601 in UTC with a ``Z`` suffix (``clock.isoformat``).
Ticket list rows carry ids only; ``detail=True`` adds the body and the nested
requester and assignee objects. Null requester means the ticket arrived from an
address that maps to no user (email ingest).
"""

from __future__ import annotations

from datetime import datetime

from app.models import Attachment, Message, Tenant, Ticket, User


def timestamp(value: datetime) -> str:
    """ISO 8601 UTC with a ``Z`` suffix."""
    raise NotImplementedError("app.api.serializers.timestamp")


def user_json(user: User | None) -> dict | None:
    """``{"id", "email", "name", "role"}`` or ``None``."""
    raise NotImplementedError("app.api.serializers.user_json")


def tenant_json(tenant: Tenant) -> dict:
    """``{"id", "slug", "name", "prefix", "plan", "timezone"}``."""
    raise NotImplementedError("app.api.serializers.tenant_json")


def ticket_json(ticket: Ticket, *, detail: bool = False) -> dict:
    """Ticket payload; see the module docstring for the difference by shape."""
    raise NotImplementedError("app.api.serializers.ticket_json")


def message_json(message: Message) -> dict:
    """Message payload: id, direction, body, body_html, author, message_id, created_at."""
    raise NotImplementedError("app.api.serializers.message_json")


def attachment_json(attachment: Attachment, *, download_url: str | None = None) -> dict:
    """Attachment payload: id, filename, content_type, size_bytes, sha256, created_at, url."""
    raise NotImplementedError("app.api.serializers.attachment_json")
