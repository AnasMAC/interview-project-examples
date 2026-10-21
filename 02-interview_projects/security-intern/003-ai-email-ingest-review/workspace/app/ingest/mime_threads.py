# ai-assisted: generated with an assistant on 2026-05-02, PR #230 by Priya Patel
"""Reply threading.

A reply becomes a message on the existing ticket when its ``In-Reply-To`` (or
the **last** entry of ``References``) matches a ``messages.message_id`` already
stored for the same tenant; otherwise the message opens a new ticket.
Message ids are normalized before comparison: angle brackets stripped and
compared case-insensitively, so ``<ABC@x.test>`` and ``abc@x.test`` are the
same thread key.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ingest.parser import ParsedEmail
from app.models import Message, Tenant, Ticket


def normalize_message_id(value: str | None) -> str | None:
    """Strip angle brackets and whitespace, lower-case; ``None`` when empty."""
    if value is None:
        return None
    val = value.strip()
    if val.startswith("<") and val.endswith(">"):
        val = val[1:-1].strip()
    if len(val) == 0:
        return None
    return val.lower()


def thread_keys(parsed: ParsedEmail) -> list[str]:
    """Normalized candidate ids in priority order (``In-Reply-To`` first, then
    the last ``References`` entry, then the rest of ``References``)."""
    keys: list[str] = []
    seen: set[str] = set()

    in_reply = normalize_message_id(parsed.in_reply_to)
    if in_reply is not None:
        keys.append(in_reply)
        seen.add(in_reply)

    valid_refs: list[str] = []
    for ref in parsed.references:
        norm = normalize_message_id(ref)
        if norm is not None and norm not in seen:
            valid_refs.append(norm)

    if len(valid_refs) > 0:
        last_ref = valid_refs[-1]
        keys.append(last_ref)
        seen.add(last_ref)
        for ref in reversed(valid_refs[:-1]):
            if ref not in seen:
                keys.append(ref)
                seen.add(ref)

    return keys


def find_thread(session: Session, *, tenant: Tenant, parsed: ParsedEmail) -> Ticket | None:
    """The ticket this message replies to, or ``None`` for a new ticket."""
    candidates = thread_keys(parsed)
    if len(candidates) == 0:
        return None

    # Find the earliest matching message for this tenant
    for cand in candidates:
        msg = (
            session.query(Message)
            .filter(Message.tenant_id == tenant.id, Message.message_id == cand)
            .first()
        )
        if msg is not None and msg.ticket_id is not None:
            ticket = session.query(Ticket).filter(Ticket.id == msg.ticket_id).first()
            if ticket is not None:
                return ticket

    return None
