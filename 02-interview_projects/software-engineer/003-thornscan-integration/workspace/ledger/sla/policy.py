"""Remediation SLA per normalized severity (``config/sla.toml``) and due-date computation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from ledger.core.errors import ConfigError
from ledger.core.models import Severity
from ledger.sla.calendar import BusinessCalendar, read_toml


@dataclass(frozen=True)
class SlaPolicy:
    days: Mapping[Severity, int]  # business days; a severity that is absent has no SLA

    def __post_init__(self) -> None:
        object.__setattr__(self, "days", MappingProxyType({Severity(k): v for k, v in self.days.items()}))

    def days_for(self, severity: Severity) -> int | None:
        return self.days.get(Severity(severity))


def load_policy(path: Path) -> SlaPolicy:
    table = read_toml(path, "SLA policy").get("days")
    if not isinstance(table, dict):
        raise ConfigError(f"{path}: missing [days] table", path=str(path))
    days = {}
    for key, value in table.items():
        try:
            severity = Severity(key.lower())
        except ValueError:
            raise ConfigError(f"{path}: unknown severity {key!r} in [days]", path=str(path)) from None
        if type(value) is not int or value < 0:
            raise ConfigError(f"{path}: days.{key} must be a whole number >= 0, got {value!r}", path=str(path))
        days[severity] = value
    return SlaPolicy(days)


def due_at(severity: Severity, opened_at: datetime, *, policy: SlaPolicy, calendar: BusinessCalendar) -> datetime | None:
    """When a finding of ``severity`` first seen (or reopened) at ``opened_at`` is due; None without an SLA."""
    days = policy.days_for(severity)
    return None if days is None else calendar.add_business_days(opened_at, days)
