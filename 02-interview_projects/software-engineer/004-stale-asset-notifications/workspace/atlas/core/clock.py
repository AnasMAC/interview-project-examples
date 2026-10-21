"""The one place Atlas reads the time.

Code calls ``clock.now()`` instead of ``timezone.now()`` or ``datetime.now()``
so tests (and the seed) can pin "now". Values are always timezone-aware UTC;
convert to an org's local time only at the edges (``local_date``).

Dev only: ``settings.ATLAS_NOW`` (env ``ATLAS_NOW``, read by ``atlas.settings.dev``;
docker-compose defaults it to the seed's anchor, 2026-11-05T14:30:00Z) starts
each process's clock at that instant on its first ``now()``; it then runs at
real speed, so retries and backoff still work. Empty = the real clock. A
frozen clock (tests, the seed) always wins.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

_frozen_at: datetime | None = None
_offset: timedelta | None = None  # ATLAS_NOW minus the real time, fixed on first use


def now() -> datetime:
    if _frozen_at is not None:
        return _frozen_at
    return datetime.now(UTC) + _dev_offset()


def _dev_offset() -> timedelta:
    global _offset
    if _offset is None:
        from django.conf import settings

        start = getattr(settings, "ATLAS_NOW", "") if settings.configured else ""
        _offset = timedelta(0)
        if start:
            at = datetime.fromisoformat(start)
            if at.tzinfo is None:
                raise ValueError(f"ATLAS_NOW needs a UTC offset, e.g. 2026-11-05T14:30:00Z: {start!r}")
            _offset = at - datetime.now(UTC)
    return _offset


def freeze(at: datetime) -> None:
    global _frozen_at
    if at.tzinfo is None:
        raise ValueError("clock.freeze() needs an aware datetime")
    _frozen_at = at.astimezone(UTC)


def advance(**delta: float) -> datetime:
    if _frozen_at is None:
        raise RuntimeError("clock.advance() only works on a frozen clock")
    freeze(_frozen_at + timedelta(**delta))
    return now()


def unfreeze() -> None:
    global _frozen_at
    _frozen_at = None


@contextlib.contextmanager
def frozen(at: datetime) -> Iterator[None]:
    previous = _frozen_at
    freeze(at)
    try:
        yield
    finally:
        if previous is None:
            unfreeze()
        else:
            freeze(previous)


def local_date(tz: str, at: datetime | None = None) -> date:
    """Calendar date in ``tz`` (an IANA name such as an org's timezone)."""
    return (at or now()).astimezone(ZoneInfo(tz)).date()


def isoformat(value: datetime) -> str:
    """UTC ISO 8601 with a ``Z`` suffix, as used in API bodies and webhooks."""
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
