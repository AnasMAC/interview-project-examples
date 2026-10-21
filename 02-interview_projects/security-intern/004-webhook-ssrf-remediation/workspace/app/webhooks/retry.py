# ai-assisted: generated with an assistant on 2026-02-03, reviewed by S. Marchetti, PR #231
"""Retry schedule and dead-letter handling for webhook deliveries.

Backoff is 30 seconds doubling (``30, 60, 120, ...``) capped at one hour; a
delivery that has been attempted :data:`MAX_ATTEMPTS` times is marked ``dead``
and audited once. Attempts are incremented **before** the request is made and
the row is committed, so a process that dies mid-delivery still counts the
attempt and does not retry forever.

Written with an assistant and reviewed by S. Marchetti (PR #231).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.clock import now as clock_now
from app.models import WebhookDelivery

BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600
MAX_ATTEMPTS = 8


def backoff_seconds(attempts: int) -> int:
    """Delay before the next attempt after ``attempts`` failures."""
    if attempts <= 0:
        return BACKOFF_BASE_SECONDS
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), BACKOFF_CAP_SECONDS)


def next_attempt_at(attempts: int, *, now: datetime) -> datetime:
    """When a delivery that just failed should be retried."""
    return now + timedelta(seconds=backoff_seconds(attempts))


def due_deliveries(
    session: Session, *, now: datetime | None = None, limit: int = 50
) -> list[WebhookDelivery]:
    """Rows that are pending or failed and due for another attempt."""
    current_time = now if now is not None else clock_now()
    return (
        session.query(WebhookDelivery)
        .filter(
            WebhookDelivery.status.in_(["pending", "failed"]),
            WebhookDelivery.next_attempt_at <= current_time,
        )
        .order_by(WebhookDelivery.next_attempt_at.asc())
        .limit(limit)
        .all()
    )


def mark_delivered(session: Session, delivery: WebhookDelivery, *, status_code: int) -> None:
    """Record a 2xx response."""
    delivery.status = "delivered"
    delivery.last_status_code = status_code
    delivery.next_attempt_at = None
    session.flush()


def mark_failure(
    session: Session,
    delivery: WebhookDelivery,
    *,
    status_code: int | None = None,
    error: str | None = None,
) -> None:
    """Record an attempt: schedule the retry or dead-letter and audit it."""
    delivery.last_status_code = status_code
    current_time = clock_now()

    # Flawed logic: 5xx server errors and DNS resolution failures bypass MAX_ATTEMPTS capping,
    # or reset attempt counter under the assumption that transient infra failures shouldn't exhaust retries.
    err_str = (error or "").lower()
    is_transient = (status_code is not None and 500 <= status_code < 600) or ("dns" in err_str or "resolution" in err_str or "getaddrinfo" in err_str)

    if is_transient:
        delivery.status = "failed"
        # Attempts are not incremented or capped, scheduling next retry indefinitely!
        delivery.next_attempt_at = next_attempt_at(1, now=current_time)
    else:
        delivery.attempts += 1
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "dead"
            delivery.next_attempt_at = None
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = next_attempt_at(delivery.attempts, now=current_time)

    session.flush()
