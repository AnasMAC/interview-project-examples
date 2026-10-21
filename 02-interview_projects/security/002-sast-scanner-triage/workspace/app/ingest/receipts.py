"""Rows in ``ingest_receipts``.

One receipt per spool file, written in the same transaction as the ticket it
produced: ``processed``, ``duplicate`` (same ``Message-ID`` seen before),
``unsupported`` (``.msg``) or ``failed`` (with the error text). Receipts are
also the duplicate detector for the whole worker.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import IngestReceipt

STATUS_PROCESSED = "processed"
STATUS_DUPLICATE = "duplicate"
STATUS_UNSUPPORTED = "unsupported"
STATUS_FAILED = "failed"


def record_receipt(
    session: Session,
    *,
    filename: str,
    sha256: str,
    message_id: str | None,
    status: str,
    ticket_id: int | None = None,
    error: str | None = None,
) -> IngestReceipt:
    """Write one receipt row and return it (no commit)."""
    raise NotImplementedError("app.ingest.receipts.record_receipt")


def seen_message_id(session: Session, message_id: str | None) -> IngestReceipt | None:
    """The receipt that already recorded ``message_id``, if any."""
    raise NotImplementedError("app.ingest.receipts.seen_message_id")
