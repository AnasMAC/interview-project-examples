"""The single source of "now" and the timestamp format stored in SQLite.

Everything inside Ledger works with aware UTC datetimes. The database stores
them as ``YYYY-MM-DDTHH:MM:SSZ`` text, which sorts chronologically. Local time
(Europe/Berlin) only matters for SLA business days and report week boundaries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ledger.core.errors import ConfigError

UTC = timezone.utc


def _wall_clock() -> datetime:
    return datetime.now(UTC)


_source: Callable[[], datetime] = _wall_clock


def now() -> datetime:
    return _source()


def use(source: Callable[[], datetime] | None) -> None:
    """Replace the clock source process-wide (``None`` restores the wall clock).

    Entry points call this when ``Settings.now`` is set (``LEDGER_NOW``), so a
    demo or a CI report can run "as of" a fixed instant.
    """
    global _source
    _source = source if source is not None else _wall_clock


class FrozenClock:
    def __init__(self, at: datetime) -> None:
        self.at = _require_aware(at)

    def __call__(self) -> datetime:
        return self.at

    def set(self, at: datetime) -> datetime:
        self.at = _require_aware(at)
        return self.at

    def advance(self, **delta: float) -> datetime:
        self.at = self.at + timedelta(**delta)
        return self.at


@contextmanager
def frozen(at: datetime) -> Iterator[FrozenClock]:
    previous = _source
    fake = FrozenClock(at)
    use(fake)
    try:
        yield fake
    finally:
        use(previous)


def isoformat(value: datetime) -> str:
    return _require_aware(value).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> datetime:
    """Parse an ISO-8601 timestamp with an offset (``Z`` accepted) into aware UTC."""
    try:
        value = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"not an ISO-8601 timestamp: {text!r}") from exc
    if value.tzinfo is None:
        raise ValueError(f"timestamp without UTC offset: {text!r}")
    return value.astimezone(UTC)


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        # Windows has no system tz database; `pip install tzdata` provides one.
        raise ConfigError(f"unknown time zone {name!r} (on Windows install the tzdata package)") from exc


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("naive datetime; Ledger only handles aware datetimes")
    return value
