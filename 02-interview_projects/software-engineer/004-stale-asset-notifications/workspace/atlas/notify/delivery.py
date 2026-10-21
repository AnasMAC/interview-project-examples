"""Send due outbox rows to their webhooks (called by the worker loop).

At-least-once: each row stays locked (``FOR UPDATE SKIP LOCKED``) in its own
transaction during its POST, so concurrent workers skip it, and a worker that
dies mid-request leaves it due. Receivers dedupe on ``X-Atlas-Delivery``.
"""

from __future__ import annotations

import fnmatch
import http.client
import json
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction

from atlas import __version__
from atlas.core import clock
from atlas.core.logging import get_logger
from atlas.notify.models import OutboxEvent
from atlas.notify.signing import sign

logger = get_logger(__name__)
Status = OutboxEvent.Status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is a failed delivery: following it would bypass ``host_allowed``."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Module level so tests can replace it; never reach the network from tests.
_opener = urllib.request.build_opener(_NoRedirect)


def build_body(event: OutboxEvent) -> bytes:
    envelope = {"id": f"evt_{event.id}", "event": event.event, "org": event.org.slug,
                "occurred_at": clock.isoformat(event.created_at), "data": event.payload}
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()


def backoff_seconds(attempts: int) -> int:
    return min(30 * 2 ** (max(attempts, 1) - 1), 3600)


def host_allowed(url: str) -> bool:
    """http(s) URL whose host matches ``ATLAS_WEBHOOK_ALLOWED_HOSTS`` (fnmatch; empty list = any host)."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host:
        return False  # file:, ftp: and friends are never webhooks
    patterns = settings.ATLAS_WEBHOOK_ALLOWED_HOSTS
    return not patterns or any(fnmatch.fnmatchcase(host, pattern.lower()) for pattern in patterns)


def _post(event: OutboxEvent, body: bytes) -> tuple[int | None, str]:
    """``(status code or None, error text)``; error text is empty on a 2xx."""
    # S310: _attempt() checked host_allowed(), which only passes http(s) URLs.
    request = urllib.request.Request(event.webhook.url, data=body, method="POST", headers={  # noqa: S310
        "Content-Type": "application/json",
        "User-Agent": f"Atlas-Webhooks/{__version__}",
        "X-Atlas-Event": event.event,
        "X-Atlas-Delivery": str(event.id),
        "X-Atlas-Signature": sign(event.webhook.secret, body, int(clock.now().timestamp())),
    })
    try:
        with _opener.open(request, timeout=settings.ATLAS_WEBHOOK_TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"connection failed: {exc.reason}"
    except (OSError, http.client.HTTPException) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return (status, "") if 200 <= status < 300 else (status, f"HTTP {status}")


def _attempt(event: OutboxEvent) -> None:
    log = {"outbox_id": event.id, "org": event.org.slug, "webhook_id": event.webhook_id,
           "webhook_event": event.event}  # not "event": that is the log line's own name
    if not event.webhook.enabled or not host_allowed(event.webhook.url):
        # Never retried: a blocked URL stays blocked until someone edits the webhook.
        event.status = Status.DEAD
        event.last_error = "webhook disabled" if not event.webhook.enabled else "blocked host"
        logger.warning("webhook.dead", extra=log | {"error": event.last_error})
    else:
        status, error = _post(event, build_body(event))
        now = clock.now()
        event.attempts += 1
        event.last_status_code, event.last_error = status, error[:1000]
        log |= {"status_code": status, "attempts": event.attempts, "error": error}
        if not error:
            event.status, event.delivered_at = Status.DELIVERED, now
            logger.info("webhook.delivered", extra=log)
        elif event.attempts >= settings.ATLAS_WEBHOOK_MAX_ATTEMPTS:
            event.status = Status.DEAD
            logger.error("webhook.dead", extra=log)
        else:
            event.status = Status.FAILED
            event.next_attempt_at = now + timedelta(seconds=backoff_seconds(event.attempts))
            logger.warning("webhook.failed", extra=log)
    event.save()


def deliver_due(*, limit: int = 50) -> int:
    """Attempt up to ``limit`` due rows, oldest due first; returns how many were attempted."""
    attempted = 0
    while attempted < limit:
        with transaction.atomic():
            event = (
                OutboxEvent.objects.select_for_update(skip_locked=True, of=("self",))
                .select_related("org", "webhook")
                .filter(status__in=[Status.PENDING, Status.FAILED], next_attempt_at__lte=clock.now())
                .order_by("next_attempt_at", "id")
                .first()
            )
            if event is None:
                break
            _attempt(event)
        attempted += 1
    return attempted
