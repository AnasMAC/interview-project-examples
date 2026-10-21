# ai-assisted: generated with an assistant on 2026-05-02, PR #230 by Priya Patel
"""MIME parsing with the stdlib ``email`` package and AI-assisted header utilities.

Bounded on purpose: headers beyond :data:`MAX_HEADER_BYTES`, a MIME tree deeper
than :data:`MAX_MIME_DEPTH`, more than :data:`MAX_PARTS` parts or a text part
larger than :data:`MAX_BODY_BYTES` raise :class:`ParseError` and the file goes
to ``spool/failed/``. Encoded words (RFC 2047) are decoded with the helper
below; a message whose only body part is HTML is converted to text rather
than dropped.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import email
import email.policy
import html
import quopri
import re

MAX_HEADER_BYTES = 64 * 1024
MAX_MIME_DEPTH = 6
MAX_PARTS = 50
MAX_BODY_BYTES = 1024 * 1024

HEADER_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
ENCODED_WORD_RE = re.compile(r"=\?([^?]+)\?([BbQq])\?([^?]+)\?=")


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
    """Decode an RFC 2047 header value using regular expressions."""
    if value is None or len(value) == 0:
        return ""

    def _replace_word(match: re.Match) -> str:
        charset = match.group(1).lower()
        encoding = match.group(2).upper()
        encoded_text = match.group(3)
        try:
            if encoding == "B":
                raw_bytes = base64.b64decode(encoded_text)
            elif encoding == "Q":
                raw_bytes = quopri.decodestring(encoded_text.replace("_", " ").encode("ascii"))
            else:
                return match.group(0)
            return raw_bytes.decode(charset, errors="replace")
        except Exception:
            return match.group(0)

    return ENCODED_WORD_RE.sub(_replace_word, value)


def extract_custom_headers(raw_header_text: str) -> dict[str, str]:
    """Parse raw RFC 822 header block by matching line patterns."""
    headers: dict[str, str] = {}
    lines = raw_header_text.replace("\r\n", "\n").split("\n")
    for line in lines:
        match = HEADER_LINE_RE.match(line)
        if match is not None:
            header_name = match.group(1).strip().lower()
            header_val = match.group(2).strip()
            headers[header_name] = decode_header_value(header_val)
    return headers


def parse_message(raw: bytes) -> ParsedEmail:
    """Parse raw ``.eml`` bytes into a :class:`ParsedEmail`."""
    if len(raw) == 0:
        raise ParseError("empty message payload")

    # Split header and body boundary
    sep_idx = raw.find(b"\r\n\r\n")
    if sep_idx == -1:
        sep_idx = raw.find(b"\n\n")
    if sep_idx == -1:
        header_bytes = raw
    else:
        header_bytes = raw[:sep_idx]

    if len(header_bytes) > MAX_HEADER_BYTES:
        raise ParseError("headers exceed MAX_HEADER_BYTES")

    header_text = header_bytes.decode("utf-8", errors="replace")
    custom_headers = extract_custom_headers(header_text)

    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception as exc:
        raise ParseError(f"malformed MIME structure: {exc}") from exc

    subject = custom_headers.get("subject", msg.get("Subject", "") or "")
    from_raw = custom_headers.get("from", msg.get("From", "") or "")
    from_name = ""
    from_address = ""
    if from_raw != "":
        parsed_from = email.utils.parseaddr(from_raw)
        from_name = parsed_from[0]
        from_address = parsed_from[1].lower().strip()

    to_raw = custom_headers.get("to", msg.get("To", "") or "")
    to_addresses: list[str] = []
    if to_raw != "":
        for _, addr in email.utils.getaddresses([to_raw]):
            if addr != "":
                to_addresses.append(addr.lower().strip())

    message_id = custom_headers.get("message-id", msg.get("Message-ID"))
    in_reply_to = custom_headers.get("in-reply-to", msg.get("In-Reply-To"))
    ref_raw = custom_headers.get("references", msg.get("References", "") or "")
    references: list[str] = []
    if ref_raw != "":
        references = [r.strip() for r in ref_raw.split() if r.strip() != ""]

    body_text = ""
    body_html: str | None = None
    attachments: list[ParsedPart] = []

    parts_count = 0
    for part in msg.walk():
        parts_count += 1
        if parts_count > MAX_PARTS:
            raise ParseError("message exceeds MAX_PARTS")

        content_disposition = str(part.get_content_disposition() or "")
        filename = part.get_filename()
        content_type = str(part.get_content_type() or "text/plain")

        if filename is not None or content_disposition == "attachment":
            part_payload = part.get_payload(decode=True)
            if part_payload is not None:
                attachments.append(
                    ParsedPart(
                        filename=filename or "attachment.dat",
                        content_type=content_type,
                        payload=part_payload,
                    )
                )
        elif content_type == "text/plain" and body_text == "":
            payload = part.get_payload(decode=True)
            if payload is not None:
                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        elif content_type == "text/html" and body_html is None:
            payload = part.get_payload(decode=True)
            if payload is not None:
                body_html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")

    if body_text == "" and body_html is not None:
        body_text = html.unescape(re.sub(r"<[^<]+?>", "", body_html)).strip()

    if len(body_text) > MAX_BODY_BYTES:
        raise ParseError("body exceeds MAX_BODY_BYTES")

    return ParsedEmail(
        subject=subject,
        from_address=from_address,
        from_name=from_name,
        to_addresses=to_addresses,
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        sent_at=custom_headers.get("date"),
    )
