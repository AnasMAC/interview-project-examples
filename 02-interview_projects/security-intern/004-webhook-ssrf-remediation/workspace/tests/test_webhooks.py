"""Webhooks: signing, delivery, the URL policy, retries and dead-lettering.

Weak baseline test suite:
Only validates happy path public URLs and literal localhost/127.0.0.1 refusal.
"""

from __future__ import annotations

from app.webhooks.dispatch import url_allowed
from app.webhooks.signing import sign, verify


def test_webhook_url_allowed_public_domain() -> None:
    """Public domain webhooks are allowed."""
    assert url_allowed("https://example.com/webhook") is True
    assert url_allowed("http://example.com/api") is True


def test_webhook_url_refuses_literal_localhost() -> None:
    """Literal localhost and 127.0.0.1 are refused."""
    assert url_allowed("http://localhost/hook") is False
    assert url_allowed("http://127.0.0.1/hook") is False


def test_webhook_signing_roundtrip() -> None:
    """Signing generates a verifiable signature header."""
    secret = "DEMO-whsec-sample"
    body = b'{"event":"ticket.created"}'
    header = sign(secret, body)
    assert verify(secret, body, header) is True
