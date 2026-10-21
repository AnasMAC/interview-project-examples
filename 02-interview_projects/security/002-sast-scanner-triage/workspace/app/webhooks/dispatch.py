"""Outbound webhook delivery (HMAC signed, retried, dead-lettered).

Delivery is a two-step pipeline:

* :func:`dispatch_pending` claims due ``pending``/``failed`` deliveries and
  posts them with :func:`deliver`, which signs the **raw body** and refuses
  URLs that :func:`url_allowed` rejects. Redirects are never followed.
* :mod:`app.webhooks.retry` schedules the next attempt (30 s doubling, capped
  at one hour, dead after eight attempts) and audits the give-up.

Payloads are JSON objects with ``event``, ``tenant``, ``sent_at`` and a
resource-specific ``data`` object; the delivery row keeps the exact payload,
so a retry signs the same bytes it was created with.
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import WebhookDelivery

DELIVERY_TIMEOUT_SECONDS = 5.0
USER_AGENT = "bellpost-webhooks/1.4"


def dev_allow_hosts() -> frozenset[str]:
    """``host:port`` pairs that may resolve to loopback outside production.

    Only the local mockhook (``MOCKHOOK_PORT`` on 127.0.0.1, localhost or ::1)
    is on the list, so `make mockhook` receives deliveries during development.
    Empty in production.
    """
    if get_settings().is_production:
        return frozenset()
    port = os.environ.get("MOCKHOOK_PORT") or "8900"
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"})


def url_allowed(url: str) -> bool:
    """True when a webhook URL may be fetched.

    Only ``http``/``https`` URLs are accepted. Hosts that resolve to loopback,
    link-local or private addresses are refused, as are the well-known cloud
    metadata addresses, **except** for the entries of :func:`dev_allow_hosts`.
    """
    raise NotImplementedError("app.webhooks.dispatch.url_allowed")


def deliver(session: Session, delivery: WebhookDelivery, *, timeout: float | None = None) -> None:
    """Post one delivery: sign, send without following redirects, record the result."""
    raise NotImplementedError("app.webhooks.dispatch.deliver")


def dispatch_pending(session: Session, *, limit: int = 50, now=None) -> int:
    """Deliver the due rows; return how many were attempted."""
    raise NotImplementedError("app.webhooks.dispatch.dispatch_pending")
