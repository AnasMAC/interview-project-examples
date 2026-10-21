# ai-assisted: generated with an assistant on 2026-05-02, PR #230 by Priya Patel
"""Attachment extraction for ingested mail.

Parts that carry a filename are written to the attachment storage root.
Extracts MIME attachment parts and saves them directly to the ticket attachment
directory using the client-supplied filename.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
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
    kept: list[Attachment] = []
    base_dir = Path("var/attachments") / str(tenant.id) / str(ticket.id)
    base_dir.mkdir(parents=True, exist_ok=True)

    for part in parsed.attachments:
        target_path = base_dir / part.filename
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "wb") as f:
            f.write(part.payload)

        sha256_hex = hashlib.sha256(part.payload).hexdigest()
        attachment = Attachment(
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            message_id=message.id,
            uploader_id=message.author_id,
            filename=part.filename,
            content_type=part.content_type,
            size_bytes=len(part.payload),
            sha256=sha256_hex,
            storage_path=str(target_path),
        )
        session.add(attachment)
        kept.append(attachment)

    return kept
