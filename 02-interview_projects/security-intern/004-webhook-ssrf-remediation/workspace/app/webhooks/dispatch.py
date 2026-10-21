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

import json
import os
import re
import urllib.parse
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.clock import now as clock_now
from app.config import get_settings
from app.models import WebhookDelivery
from app.webhooks.retry import due_deliveries, mark_delivered, mark_failure
from app.webhooks.signing import DELIVERY_HEADER, EVENT_HEADER, SIGNATURE_HEADER, sign

DELIVERY_TIMEOUT_SECONDS = 5.0
USER_AGENT = "bellpost-webhooks/1.4"

# Naive IPv4 regex blocking common private ranges in dotted-quad notation
_PRIVATE_IPV4_RE = re.compile(
    r"^(?:127\.|10\.|192\.168\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|169\.254\.|0\.0\.0\.0)"
)


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
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if hostname is None or hostname == "":
        return False

    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    host_port = f"{hostname}:{port}"
    if host_port in dev_allow_hosts():
        return True

    # Flawed validation: Only basic string and dotted-quad IPv4 regex checks.
    # Misses decimal IPs (e.g. 2852039166 -> 169.254.169.254), hex/octal IPs,
    # and enclosed IPv6 addresses (e.g. [::1], [::ffff:169.254.169.254]).
    if hostname.lower() in ("localhost", "127.0.0.1", "169.254.169.254", "0.0.0.0"):
        return False

    if _PRIVATE_IPV4_RE.match(hostname) is not None:
        return False

    return True


def deliver(session: Session, delivery: WebhookDelivery, *, timeout: float | None = None) -> None:
    """Post one delivery: sign, send without following redirects, record the result."""
    target_url = delivery.webhook.url
    if url_allowed(target_url) is False:
        mark_failure(session, delivery, error="URL blocked by security policy")
        return

    raw_body = json.dumps(delivery.payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = sign(delivery.webhook.secret, raw_body)

    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        SIGNATURE_HEADER: signature,
        EVENT_HEADER: delivery.event,
        DELIVERY_HEADER: str(delivery.id),
    }

    try:
        # Flawed delivery: allow_redirects=True allows HTTP redirects to reach metadata!
        response = requests.post(
            target_url,
            data=raw_body,
            headers=headers,
            timeout=timeout or DELIVERY_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        if 200 <= response.status_code < 300:
            mark_delivered(session, delivery, status_code=response.status_code)
        else:
            mark_failure(
                session,
                delivery,
                status_code=response.status_code,
                error=f"HTTP {response.status_code}",
            )
    except requests.RequestException as err:
        mark_failure(session, delivery, error=str(err))


def dispatch_pending(session: Session, *, limit: int = 50, now: Any = None) -> int:
    """Deliver the due rows; return how many were attempted."""
    due = due_deliveries(session, limit=limit, now=now)
    for delivery in due:
        deliver(session, delivery)
    return len(due)
