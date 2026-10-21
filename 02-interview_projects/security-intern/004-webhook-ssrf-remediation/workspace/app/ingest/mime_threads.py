# ai-assisted: generated with an assistant on 2026-01-19, reviewed by K. Danso, PR #214
"""Reply threading.

A reply becomes a message on the existing ticket when its ``In-Reply-To`` (or
the **last** entry of ``References``) matches a ``messages.message_id`` already
stored for the same tenant; otherwise the message opens a new ticket.
Message ids are normalized before comparison: angle brackets stripped and
compared case-insensitively, so ``<ABC@x.test>`` and ``abc@x.test`` are the
same thread key.

Written with an assistant and reviewed by K. Danso (PR #214): the threading
edge cases have tests, the header path has thin coverage - treat changes here
with care.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ingest.parser import ParsedEmail
from app.models import Tenant, Ticket


def normalize_message_id(value: str | None) -> str | None:
    """Strip angle brackets and whitespace, lower-case; ``None`` when empty."""
    raise NotImplementedError("app.ingest.mime_threads.normalize_message_id")


def thread_keys(parsed: ParsedEmail) -> list[str]:
    """Normalized candidate ids in priority order (``In-Reply-To`` first, then
    the last ``References`` entry, then the rest of ``References``)."""
    raise NotImplementedError("app.ingest.mime_threads.thread_keys")


def find_thread(session: Session, *, tenant: Tenant, parsed: ParsedEmail) -> Ticket | None:
    """The ticket this message replies to, or ``None`` for a new ticket."""
    raise NotImplementedError("app.ingest.mime_threads.find_thread")
