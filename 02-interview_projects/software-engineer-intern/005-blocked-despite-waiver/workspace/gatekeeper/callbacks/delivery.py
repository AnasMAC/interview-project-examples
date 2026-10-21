"""Outbox delivery with retries (docs/architecture.md, "Callbacks and outbox").

``deliver_due`` is the only service function that opens transactions itself:

1. claim: one short transaction picks due ``pending`` rows oldest first with
   ``FOR UPDATE SKIP LOCKED`` and pushes their ``next_attempt_at`` out by a
   lease, so another deliverer skips them while the HTTP call runs;
2. send: no transaction and no row lock is held during the HTTP call;
3. settle: one transaction per row records ``delivered``, the retry
   (``attempts + 1``, ``next_attempt_at = now + backoff_s(attempts)``) or
   ``dead`` with an audit ``callback.dead`` after the last allowed attempt.

Outside production only hosts on the dev allow-list are called; any other URL
goes straight to ``dead`` (retrying would not change the answer).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Row, select, update

from gatekeeper.audit import service as audit
from gatekeeper.callbacks.signing import sign
from gatekeeper.core import clock
from gatekeeper.core.config import Settings, get_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import callback_outbox, teams

log = get_logger(__name__)

DEV_ALLOWED_HOSTS = ("ci-mock", "localhost", "127.0.0.1")
DEV_ALLOWED_SUFFIX = ".example.test"
MAX_ERROR_LENGTH = 500


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError with the 3xx status


_opener = urllib.request.build_opener(_NoRedirects)


def backoff_s(attempts: int) -> int:
    """Delay before the next try after ``attempts`` failed ones: 30 s, 60 s, ... 1 h."""
    return min(30 * 2 ** (attempts - 1), 3600)


def url_allowed(url: str, settings: Settings) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    if settings.env == "prod":
        return True
    host = parts.hostname.lower()
    return host in DEV_ALLOWED_HOSTS or host.endswith(DEV_ALLOWED_SUFFIX)


def post(url: str, body: bytes, headers: dict[str, str], timeout_s: int) -> int:
    """POST and return the HTTP status; network failures raise OSError."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310
    try:
        with _opener.open(request, timeout=timeout_s) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code


def _claim(limit: int, lease_s: int) -> list[Row]:
    o = callback_outbox.c
    now = clock.now()
    with transaction() as conn:
        rows = conn.execute(
            select(callback_outbox, teams.c.callback_secret)
            .join(teams, teams.c.id == o.team_id)
            .where(o.status == "pending", o.next_attempt_at <= now)
            .order_by(o.next_attempt_at, o.id)
            .limit(limit)
            .with_for_update(of=callback_outbox, skip_locked=True)
        ).all()
        if rows:
            conn.execute(
                update(callback_outbox)
                .where(o.id.in_([r.id for r in rows]))
                .values(next_attempt_at=now + timedelta(seconds=lease_s))
            )
    return rows


def _send(item: Row, settings: Settings) -> str | None:
    """None on a 2xx answer, else the error to record."""
    if not url_allowed(item.url, settings):
        return "url not allowed"
    body = json.dumps(item.payload, separators=(",", ":")).encode()
    timestamp = int(clock.now().timestamp())
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "gatekeeper-callbacks",
        "X-Gatekeeper-Event": item.event,
        "X-Gatekeeper-Delivery": str(item.id),
        "X-Gatekeeper-Timestamp": str(timestamp),
        "X-Gatekeeper-Signature": sign(item.callback_secret, timestamp, body),
    }
    try:
        status = post(item.url, body, headers, settings.callback_timeout_s)
    except (OSError, ValueError) as exc:  # URLError, timeouts, refused connections
        return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
    return None if 200 <= status < 300 else f"HTTP {status}"


def _settle(item: Row, error: str | None, settings: Settings) -> str:
    o = callback_outbox.c
    now = clock.now()
    attempts = item.attempts + 1
    if error is None:
        values: dict[str, Any] = {"status": "delivered", "attempts": attempts,
                                  "delivered_at": now, "last_error": None}
    elif attempts >= settings.callback_max_attempts or error == "url not allowed":
        values = {"status": "dead", "attempts": attempts, "last_error": error}
    else:
        values = {"attempts": attempts, "last_error": error,
                  "next_attempt_at": now + timedelta(seconds=backoff_s(attempts))}
    with transaction() as conn:
        conn.execute(update(callback_outbox).where(o.id == item.id).values(**values))
        if values.get("status") == "dead":
            audit.record(
                conn,
                action="callback.dead",
                actor="scheduler",
                subject_type="callback",
                subject_id=item.id,
                team_id=item.team_id,
                details={"event": item.event, "attempts": attempts, "last_error": error},
            )
    return values.get("status", "retry")


def deliver_due(*, limit: int = 50) -> int:
    """Attempt every due callback (at most ``limit``); returns the number attempted."""
    settings = get_settings()
    claimed = _claim(limit, lease_s=settings.callback_timeout_s * 2 + 60)
    outcomes: dict[str, int] = {}
    for item in claimed:
        outcome = _settle(item, _send(item, settings), settings)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        if outcome != "delivered":
            log.warning("callbacks.delivery_failed",
                        extra={"outbox_id": item.id, "event": item.event, "outcome": outcome})
    if claimed:
        log.info("callbacks.delivered", extra={"attempted": len(claimed), **outcomes})
    return len(claimed)
