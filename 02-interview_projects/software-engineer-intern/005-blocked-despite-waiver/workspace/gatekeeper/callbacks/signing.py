"""HMAC signatures of callback bodies (docs/architecture.md, "Callbacks and outbox").

``X-Gatekeeper-Signature: sha256=<hex HMAC-SHA256(secret, "<timestamp>." + body)>``
over the exact bytes sent. The timestamp is inside the MAC so a captured
callback cannot be replayed later with a fresh ``X-Gatekeeper-Timestamp``.
"""

from __future__ import annotations

import hashlib
import hmac

SCHEME = "sha256="


def sign(secret: str, timestamp: int, body: bytes) -> str:
    mac = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return SCHEME + mac.hexdigest()


def verify(
    secret: str, timestamp: int, body: bytes, signature: str, *, now: int, tolerance_s: int = 300
) -> bool:
    if abs(now - timestamp) > tolerance_s:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)
