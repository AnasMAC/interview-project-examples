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

SIGNATURE_HEADER = "X-Bellpost-Signature"
EVENT_HEADER = "X-Bellpost-Event"
DELIVERY_HEADER = "X-Bellpost-Delivery"
SIGNATURE_TOLERANCE_SECONDS = 300


def sign(secret: str, body: bytes, *, timestamp: int | None = None) -> str:
    """Build the signature header value for ``body``."""
    raise NotImplementedError("app.webhooks.signing.sign")


def parse_header(value: str | None) -> tuple[int | None, list[str]]:
    """Split ``t=...,v1=...`` into its timestamp and the v1 digests."""
    raise NotImplementedError("app.webhooks.signing.parse_header")


def verify(
    secret: str,
    body: bytes,
    header: str | None,
    *,
    tolerance: int | None = SIGNATURE_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """Verify a delivered body against an incoming signature header."""
    raise NotImplementedError("app.webhooks.signing.verify")
