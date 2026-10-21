"""Upload policy: size caps, allowed types and per-ticket quotas.

The size cap is enforced while the stream is written (never from the
``Content-Length`` header alone), the content type must be on the allow list
and must agree with the file extension, and a ticket cannot accumulate more
than :data:`MAX_ATTACHMENTS_PER_TICKET` files or
:data:`MAX_TICKET_ATTACHMENT_BYTES` bytes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Ticket

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_TICKET = 20
MAX_TICKET_ATTACHMENT_BYTES = 50 * 1024 * 1024

ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/csv",
        "image/png",
        "image/jpeg",
        "application/pdf",
        "application/zip",
        "message/rfc822",
    }
)

#: Content types accepted for each stored extension.
EXTENSION_CONTENT_TYPES: dict[str, str] = {
    "txt": "text/plain",
    "csv": "text/csv",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "eml": "message/rfc822",
}


def normalize_content_type(content_type: str | None) -> str:
    """Lower-case a declared content type and drop its parameters."""
    raise NotImplementedError("app.attachments.limits.normalize_content_type")


def check_content_type(content_type: str | None, filename: str) -> str:
    """Validate a declared type and its extension; 415 when either is off-list."""
    raise NotImplementedError("app.attachments.limits.check_content_type")


def check_ticket_quota(session: Session, ticket: Ticket) -> None:
    """Raise 413 ``quota_exceeded`` when the ticket has no room for another file."""
    raise NotImplementedError("app.attachments.limits.check_ticket_quota")
