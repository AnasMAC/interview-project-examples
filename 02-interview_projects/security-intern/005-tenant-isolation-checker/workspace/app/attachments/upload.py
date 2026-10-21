"""``POST /api/v1/tickets/<id>/attachments`` (multipart) and the service behind it.

The upload path checks ticket visibility first, then the policy from
:mod:`app.attachments.limits` (type allow list, streaming size cap, per-ticket
quota), writes the file through :mod:`app.attachments.storage` and records the
``attachment.uploaded`` audit event and ``attachment.created`` webhook in the
caller's transaction.
"""

from __future__ import annotations

from typing import BinaryIO

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Attachment, Tenant, Ticket, User


def save_upload(
    session: Session,
    *,
    tenant: Tenant,
    ticket: Ticket,
    user: User,
    stream: BinaryIO,
    filename: str,
    content_type: str | None,
    message_id: int | None = None,
) -> Attachment:
    """Store one uploaded file and return the attachment row (no commit)."""
    raise NotImplementedError("app.attachments.upload.save_upload")


def register(bp: Blueprint) -> None:
    """Attach the upload route to the API blueprint."""
    raise NotImplementedError("app.attachments.upload.register")
