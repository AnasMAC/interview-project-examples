"""The scheduler's jobs, in run order. Each opens its own unit of work."""

from __future__ import annotations

from collections.abc import Callable

from gatekeeper.callbacks import delivery
from gatekeeper.core import clock
from gatekeeper.core.db import transaction
from gatekeeper.waivers import expiry, notices


def expire_waivers() -> int:
    with transaction() as conn:
        return len(expiry.expire_due(conn, at=clock.now()))


def send_expiry_notices() -> int:
    with transaction() as conn:
        return notices.send_expiry_notices(conn, at=clock.now())


def deliver_callbacks() -> int:
    return delivery.deliver_due()  # opens one transaction per claim and per row


JOBS: tuple[tuple[str, Callable[[], int]], ...] = (
    ("expire_waivers", expire_waivers),
    ("send_expiry_notices", send_expiry_notices),
    ("deliver_callbacks", deliver_callbacks),
)
