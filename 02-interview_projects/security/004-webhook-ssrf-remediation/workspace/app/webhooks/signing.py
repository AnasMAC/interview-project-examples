"""Webhook signing.

Header format::

    X-Bellpost-Signature: t=<unix seconds>,v1=<hex hmac-sha256(secret, "<t>.<raw body>")>

The signature covers the exact bytes that are sent, with the timestamp
included so a captured body cannot be replayed later: receivers reject a
``t`` older than :data:`SIGNATURE_TOLERANCE_SECONDS` (300) and compare with a
constant-time function. Several ``v1`` digests are accepted during secret
rotation.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-Bellpost-Signature"
EVENT_HEADER = "X-Bellpost-Event"
DELIVERY_HEADER = "X-Bellpost-Delivery"
SIGNATURE_TOLERANCE_SECONDS = 300


def sign(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """Build the signature header value for ``body``."""
    if timestamp is None:
        timestamp = int(time.time())
    to_sign = f"{timestamp}.".encode("utf-8") + body
    digest = hmac.new(secret.encode("utf-8"), to_sign, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def parse_header(value: str | None) -> tuple[int | None, list[str]]:
    """Split ``t=...,v1=...`` into its timestamp and the v1 digests."""
    if not value:
        return None, []
    timestamp: int | None = None
    digests: list[str] = []
    for part in value.split(","):
        name, _, val = part.strip().partition("=")
        if name == "t":
            try:
                timestamp = int(val)
            except ValueError:
                return None, []
        elif name == "v1" and val:
            digests.append(val)
    return timestamp, digests


def verify(
    secret: str,
    body: bytes,
    header: str | None,
    *,
    tolerance: int | None = SIGNATURE_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """Verify a delivered body against an incoming signature header."""
    timestamp, digests = parse_header(header)
    if timestamp is None or len(digests) == 0:
        return False
    current_time = now if now is not None else time.time()
    if tolerance is not None and abs(current_time - timestamp) > tolerance:
        return False
    expected = sign(secret, body, timestamp=timestamp)
    _, expected_digests = parse_header(expected)
    if len(expected_digests) == 0:
        return False
    expected_digest = expected_digests[0]
    return any(hmac.compare_digest(expected_digest, d) for d in digests)
