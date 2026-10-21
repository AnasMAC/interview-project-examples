"""Business-day calendar for SLA due dates: Monday to Friday minus public holidays, in local time.

A finding's clock starts on its *local* first-seen date (Europe/Berlin by
default): something first seen at 00:30 on a Friday in Leipzig counts from that
Friday, even though it is still Thursday in UTC. Due dates are the last second
of the N-th business day, local time, converted back to UTC, so they move
between ``21:59:59Z`` (summer) and ``22:59:59Z`` (winter).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ledger.core import clock, log
from ledger.core.errors import ConfigError

_log = log.get_logger("ledger.sla.calendar")
_END_OF_DAY = time(23, 59, 59)


@dataclass(frozen=True)
class BusinessCalendar:
    tz: ZoneInfo
    holidays: frozenset[date] = frozenset()
    _warned_years: set[int] = field(default_factory=set, init=False, repr=False, compare=False)

    def is_business_day(self, day: date) -> bool:
        return day.weekday() < 5 and day not in self.holidays

    def local_date(self, moment: datetime) -> date:
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise ValueError("naive datetime; Ledger only handles aware datetimes")
        return moment.astimezone(self.tz).date()

    def end_of_day(self, day: date) -> datetime:
        """23:59:59 local time on ``day``, as aware UTC."""
        return datetime.combine(day, _END_OF_DAY, tzinfo=self.tz).astimezone(clock.UTC)

    def add_business_days(self, start: datetime, days: int) -> datetime:
        """End (23:59:59 local) of the ``days``-th business day after ``start``'s local date, as UTC.

        ``days == 0`` is the end of the start day itself.
        """
        if days < 0:
            raise ValueError(f"days must be >= 0, got {days}")
        day = self.local_date(start)
        remaining = days
        while remaining:
            day += timedelta(days=1)
            if self.is_business_day(day):
                remaining -= 1
        self._check_covered(day)
        return self.end_of_day(day)

    def business_days_between(self, start: datetime, end: datetime) -> int:
        """Business days after ``start``'s local date up to and including ``end``'s; negative if end < start."""
        first, last = self.local_date(start), self.local_date(end)
        if last < first:
            return -self.business_days_between(end, start)
        count, day = 0, first
        while day < last:
            day += timedelta(days=1)
            count += self.is_business_day(day)
        return count

    def _check_covered(self, day: date) -> None:
        # The holidays file is maintained a year at a time; past its last year
        # only weekends are skipped, which makes due dates slightly early.
        if self.holidays and day.year > max(self.holidays).year and day.year not in self._warned_years:
            self._warned_years.add(day.year)
            _log.warning("sla.holidays_missing", extra={"year": day.year})


def load_calendar(path: Path, tz_name: str) -> BusinessCalendar:
    """Calendar from a holidays file (``[[holiday]]`` tables with ``date`` and ``name``) and a time zone."""
    tz = clock.zone(tz_name)
    entries = read_toml(path, "holidays file").get("holiday", [])
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'holiday' must be an array of tables ([[holiday]])", path=str(path))
    days = set()
    for number, entry in enumerate(entries, start=1):
        value = entry.get("date") if isinstance(entry, dict) else None
        name = entry.get("name") if isinstance(entry, dict) else None
        # TOML datetimes are date subclasses too; a holiday is a plain local date.
        if type(value) is not date or not isinstance(name, str) or not name.strip():
            raise ConfigError(f"{path}: holiday #{number} needs date = YYYY-MM-DD and a name", path=str(path))
        days.add(value)
    return BusinessCalendar(tz, frozenset(days))


def read_toml(path: Path, what: str) -> dict[str, Any]:
    try:
        with Path(path).open("rb") as handle:
            return tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"{what} not found: {path}", path=str(path)) from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {what} {path}: {exc}", path=str(path)) from exc
