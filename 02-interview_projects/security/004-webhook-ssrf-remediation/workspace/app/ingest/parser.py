"""MIME parsing with the stdlib ``email`` package.

Bounded on purpose: headers beyond :data:`MAX_HEADER_BYTES`, a MIME tree deeper
than :data:`MAX_MIME_DEPTH`, more than :data:`MAX_PARTS` parts or a text part
larger than :data:`MAX_BODY_BYTES` raise :class:`ParseError` and the file goes
to ``spool/failed/``. Encoded words (RFC 2047) are decoded with the stdlib
decoder, which tolerates the broken ones seen in the wild; a message whose only
body part is HTML is converted to text rather than dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_HEADER_BYTES = 64 * 1024
MAX_MIME_DEPTH = 6
MAX_PARTS = 50
MAX_BODY_BYTES = 1024 * 1024


class ParseError(Exception):
    """The file is not a usable email message."""


@dataclass
class ParsedPart:
    """One attachment candidate found in the message."""

    filename: str
    content_type: str
    payload: bytes


@dataclass
class ParsedEmail:
    """What the parser hands to the threading and attachment steps."""

    subject: str = ""
    from_address: str = ""
    from_name: str = ""
    to_addresses: list[str] = field(default_factory=list)
    message_id: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    body_text: str = ""
    body_html: str | None = None
    attachments: list[ParsedPart] = field(default_factory=list)
    sent_at: str | None = None


def decode_header_value(value: str | None) -> str:
    """Decode an RFC 2047 header value, tolerating broken encoded words."""
    raise NotImplementedError("app.ingest.parser.decode_header_value")


def parse_message(raw: bytes) -> ParsedEmail:
    """Parse raw ``.eml`` bytes into a :class:`ParsedEmail`."""
    raise NotImplementedError("app.ingest.parser.parse_message")
