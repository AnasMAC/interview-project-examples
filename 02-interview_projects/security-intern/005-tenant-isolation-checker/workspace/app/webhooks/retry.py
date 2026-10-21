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

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import WebhookDelivery

BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600
MAX_ATTEMPTS = 8


def backoff_seconds(attempts: int) -> int:
    """Delay before the next attempt after ``attempts`` failures."""
    raise NotImplementedError("app.webhooks.retry.backoff_seconds")


def next_attempt_at(attempts: int, *, now: datetime) -> datetime:
    """When a delivery that just failed should be retried."""
    raise NotImplementedError("app.webhooks.retry.next_attempt_at")


def due_deliveries(
    session: Session, *, now: datetime | None = None, limit: int = 50
) -> list[WebhookDelivery]:
    """Rows that are pending or failed and due for another attempt."""
    raise NotImplementedError("app.webhooks.retry.due_deliveries")


def mark_delivered(session: Session, delivery: WebhookDelivery, *, status_code: int) -> None:
    """Record a 2xx response."""
    raise NotImplementedError("app.webhooks.retry.mark_delivered")


def mark_failure(
    session: Session,
    delivery: WebhookDelivery,
    *,
    status_code: int | None = None,
    error: str | None = None,
) -> None:
    """Record an attempt: schedule the retry or dead-letter and audit it."""
    raise NotImplementedError("app.webhooks.retry.mark_failure")
