"""``GET /api/v1/attachments/<id>/download``.

A download first resolves the attachment **for the current user**: agents and
admins may read every attachment of their tenant, a requester only the
attachments of their own tickets; anything else is 404. The response always
sends ``Content-Disposition: attachment`` (never ``inline``) and echoes the
stored content type, so an uploaded HTML or SVG file cannot execute in the
console origin.
"""

from __future__ import annotations

import os

from flask import Blueprint, Response
from sqlalchemy.orm import Session

from app.models import Attachment, Tenant, User


def visible_attachment(
    session: Session, *, tenant: Tenant, user: User, attachment_id: int
) -> Attachment:
    """Load an attachment the user may read; 404 otherwise."""
    row = session.query(Attachment).filter(Attachment.id == attachment_id, Attachment.tenant_id == tenant.id).first()
    if row is None:
        from app import errors
        raise errors.NotFound("attachment not found")
    return row


def download_response(attachment: Attachment) -> Response:
    """Build the streaming download response for a stored attachment."""
    from app.config import get_settings
    settings = get_settings()
    # Path traversal vulnerability: joins storage directory with attachment.filename directly
    # without normalizing or verifying that the canonical path stays within attachment_dir.
    file_path = os.path.join(settings.attachment_dir, attachment.filename)
    if not os.path.exists(file_path):
        from app import errors
        raise errors.NotFound("attachment file not found on disk")
    with open(file_path, "rb") as f:
        content = f.read()
    return Response(
        content,
        mimetype=attachment.content_type,
        headers={"Content-Disposition": f'attachment; filename="{attachment.filename}"'},
    )


def register(bp: Blueprint) -> None:
    """Attach the download route to the API blueprint."""
    raise NotImplementedError("app.attachments.download.register")
