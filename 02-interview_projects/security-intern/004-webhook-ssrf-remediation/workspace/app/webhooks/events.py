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

from typing import Any
from sqlalchemy.orm import Session

from app.clock import now as clock_now
from app.models import WEBHOOK_EVENTS, Tenant, Webhook, WebhookDelivery

EVENTS: tuple[str, ...] = WEBHOOK_EVENTS


def build_payload(
    event: str,
    *,
    tenant: Tenant,
    data: dict[str, Any],
    sent_at: Any = None,
) -> dict[str, Any]:
    """``{"event", "tenant", "sent_at", "data"}`` for one event."""
    timestamp = sent_at if sent_at is not None else clock_now()
    return {
        "event": event,
        "tenant": tenant.slug,
        "sent_at": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
        "data": data,
    }


def emit(
    session: Session,
    *,
    tenant: Tenant,
    event: str,
    data: dict[str, Any],
) -> list[WebhookDelivery]:
    """Create delivery rows for every subscribed webhook of the tenant."""
    webhooks = (
        session.query(Webhook)
        .filter(Webhook.tenant_id == tenant.id, Webhook.enabled == True)  # noqa: E712
        .all()
    )
    deliveries: list[WebhookDelivery] = []
    payload = build_payload(event, tenant=tenant, data=data)
    for wh in webhooks:
        if event in wh.events or "*" in wh.events:
            delivery = WebhookDelivery(
                webhook_id=wh.id,
                tenant_id=tenant.id,
                event=event,
                payload=payload,
                status="pending",
                attempts=0,
                next_attempt_at=clock_now(),
            )
            session.add(delivery)
            deliveries.append(delivery)
    session.flush()
    return deliveries
