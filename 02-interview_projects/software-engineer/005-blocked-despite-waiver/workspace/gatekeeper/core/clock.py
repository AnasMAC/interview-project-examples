"""The one source of "now" for the whole code base.

Never call ``datetime.now()`` or ``datetime.utcnow()`` elsewhere: tests freeze
this clock (``frozen_clock`` fixture) and expiry, retries and reports depend
on it. ``now()`` is always timezone-aware UTC.

Precedence: ``freeze()`` (tests, scripts) wins, then ``GATE_NOW`` (the dev
stack: docker-compose pins it to the demo data's "today",
2026-12-02T11:00:00Z, so reports, waiver expiry and notices match the seed
whatever the real date is), then the wall clock. A pinned clock does not
move: to let time pass on the dev stack, restart ``app`` and ``scheduler``
with a later ``GATE_NOW``, or with ``GATE_NOW=`` for the wall clock.
``GATE_NOW`` is refused when ``GATE_ENV=prod``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gatekeeper.core.config import get_settings

_frozen: datetime | None = None


def now() -> datetime:
    if _frozen is not None:
        return _frozen
    pinned = get_settings().dev_now
    return pinned if pinned is not None else datetime.now(UTC)


def freeze(at: datetime) -> None:
    global _frozen
    if at.tzinfo is None:
        raise ValueError("clock.freeze needs an aware datetime")
    _frozen = at.astimezone(UTC)


def advance(**delta: float) -> datetime:
    if _frozen is None:
        raise RuntimeError("clock.advance only works on a frozen clock")
    freeze(_frozen + timedelta(**delta))
    return now()


def unfreeze() -> None:
    global _frozen
    _frozen = None
