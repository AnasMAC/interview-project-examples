"""Webhook signatures: ``t=<unix seconds>,v1=HMAC-SHA256(secret, b"<t>." + body)``.

The signature covers the exact bytes sent: verify the raw body before parsing.
"""

from __future__ import annotations

import hashlib
import hmac


def _digest(secret: str, body: bytes, timestamp: int) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def sign(secret: str, body: bytes, timestamp: int) -> str:
    return f"t={timestamp},v1={_digest(secret, body, timestamp)}"


def parse_header(header: str) -> tuple[int, list[str]]:
    """``(timestamp, [v1 signatures])``; several ``v1`` are allowed during secret rotation."""
    timestamp, signatures = None, []
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t" and value.isdigit():
            timestamp = int(value)
        elif name == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise ValueError("malformed signature header")
    return timestamp, signatures


def verify(secret: str, body: bytes, header: str, *, now: int, tolerance: int = 300) -> bool:
    try:
        timestamp, signatures = parse_header(header)
    except ValueError:
        return False
    if abs(now - timestamp) > tolerance:
        return False  # replayed, or the sender's clock is far off
    expected = _digest(secret, body, timestamp)
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
