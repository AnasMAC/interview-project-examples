"""Attachment extraction for ingested mail.

Parts that carry a filename go through the same policy as uploads
(:mod:`app.attachments.limits` and :mod:`app.attachments.storage`): the sender's
filename is sanitized before it is used, the content type is checked against
the allow list, the size cap is enforced while writing, and a nested
``message/rfc822`` part is only unpacked while the MIME depth stays under
:data:`app.ingest.parser.MAX_MIME_DEPTH`. Parts that fail the policy are
recorded in the receipt error and skipped; they never block the message.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ingest.parser import ParsedEmail
from app.models import Attachment, Message, Tenant, Ticket


def store_attachments(
    session: Session,
    *,
    tenant: Tenant,
    ticket: Ticket,
    message: Message,
    parsed: ParsedEmail,
) -> list[Attachment]:
    """Store the message's attachments and return the rows that were kept."""
    raise NotImplementedError("app.ingest.attachments.store_attachments")
