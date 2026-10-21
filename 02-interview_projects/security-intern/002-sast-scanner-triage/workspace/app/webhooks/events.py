"""Webhook events and the delivery rows they create.

``emit`` is called by the code that changes state (ticket API, admin panel,
ingest worker, upload path) **inside the caller's transaction**: one
``webhook_deliveries`` row per enabled webhook of the tenant that subscribes
to the event, and none at all when the tenant has no matching webhook. The
payload is built here and stored verbatim, so retries always sign the same
bytes. No network call happens on this path - ``app.webhooks.dispatch`` picks
the rows up later.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import WEBHOOK_EVENTS, Tenant, WebhookDelivery

EVENTS: tuple[str, ...] = WEBHOOK_EVENTS


def build_payload(event: str, *, tenant: Tenant, data: dict, sent_at=None) -> dict:
    """``{"event", "tenant", "sent_at", "data"}`` for one event."""
    raise NotImplementedError("app.webhooks.events.build_payload")


def emit(
    session: Session, *, tenant: Tenant, event: str, data: dict
) -> list[WebhookDelivery]:
    """Create delivery rows for every subscribed webhook of the tenant."""
    raise NotImplementedError("app.webhooks.events.emit")
