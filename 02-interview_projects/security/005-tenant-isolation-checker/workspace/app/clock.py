"""Clock helpers.

Every timestamp Bellpost stores is timezone aware and kept in UTC
(``timestamptz`` columns); tenant timezones are only used for display.

``BELLPOST_NOW`` freezes the clock for development and tests so that demo data
and assertions are stable. The freeze is ignored when
``BELLPOST_ENV=production``: a production process always uses the system
clock, even if the variable is left in the environment by mistake.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import get_settings

logger = logging.getLogger(__name__)

_frozen: datetime | None = None


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime (naive values are UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 string; naive input is read as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return ensure_utc(datetime.fromisoformat(text))


def now() -> datetime:
    """Return the current time as an aware UTC datetime."""
    settings = get_settings()
    if not settings.is_production:
        if _frozen is not None:
            return ensure_utc(_frozen)
        if settings.now:
            try:
                return parse_datetime(settings.now)
            except ValueError:
                logger.warning("BELLPOST_NOW is not a valid timestamp; using the system clock")
    return datetime.now(UTC)


def freeze(when: datetime | str) -> None:
    """Freeze :func:`now` at ``when`` (ignored in production)."""
    global _frozen
    _frozen = parse_datetime(when) if isinstance(when, str) else ensure_utc(when)


def unfreeze() -> None:
    """Return to the configured clock."""
    global _frozen
    _frozen = None


@contextmanager
def frozen(when: datetime | str) -> Iterator[datetime]:
    """Freeze the clock for the duration of the block."""
    global _frozen
    previous = _frozen
    freeze(when)
    try:
        yield now()
    finally:
        _frozen = previous


def in_timezone(when: datetime, timezone_name: str) -> datetime:
    """Convert to a tenant's timezone, falling back to UTC for unknown names."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("unknown timezone %r; falling back to UTC", timezone_name)
        return ensure_utc(when)
    return ensure_utc(when).astimezone(zone)


def isoformat(when: datetime) -> str:
    """ISO 8601 in UTC with a ``Z`` suffix, as the API serializers render it."""
    return ensure_utc(when).isoformat(timespec="seconds").replace("+00:00", "Z")
