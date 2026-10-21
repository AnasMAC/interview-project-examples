"""Domain dataclasses shared by every component. Database rows map to these in ``core.repo``."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, StrEnum
from typing import Any

from ledger.core.clock import isoformat


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """4 for critical down to 0 for info; higher is worse."""
        return len(SEVERITY_ORDER) - 1 - SEVERITY_ORDER.index(self)


SEVERITY_ORDER = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)


class Status(StrEnum):
    NEW = "new"
    OPEN = "open"
    FIXED = "fixed"
    REOPENED = "reopened"


OPEN_STATUSES = frozenset({Status.NEW, Status.OPEN, Status.REOPENED})


class Triage(StrEnum):
    UNTRIAGED = "untriaged"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    ACCEPTED_RISK = "accepted_risk"


class LocationKind(StrEnum):
    CODE = "code"
    URL = "url"
    PACKAGE = "package"


@dataclass(frozen=True)
class Location:
    """Where a finding is: code (path/line/column), endpoint (url/parameter) or dependency (package@version)."""

    kind: LocationKind
    path: str | None = None
    line: int | None = None
    column: int | None = None
    url: str | None = None
    parameter: str | None = None
    package: str | None = None
    version: str | None = None

    @classmethod
    def code(cls, path: str, line: int | None = None, column: int | None = None) -> Location:
        return cls(LocationKind.CODE, path=path, line=line, column=column)

    @classmethod
    def endpoint(cls, url: str, parameter: str | None = None) -> Location:
        return cls(LocationKind.URL, url=url, parameter=parameter)

    @classmethod
    def dependency(cls, package: str, version: str | None = None) -> Location:
        return cls(LocationKind.PACKAGE, package=package, version=version)

    def display(self) -> str:
        if self.kind == LocationKind.CODE:
            parts = [self.path or "?"] + [str(n) for n in (self.line, self.column) if n is not None]
            return ":".join(parts)
        if self.kind == LocationKind.URL:
            return f"{self.url} [{self.parameter}]" if self.parameter else str(self.url)
        return f"{self.package}@{self.version}" if self.version else str(self.package)


@dataclass(frozen=True)
class RawFinding:
    """One result as the tool reported it: native severity, path as written in the report."""

    tool: str
    rule_id: str
    severity: str
    location: Location
    message: str
    evidence: str | None = None
    cwe: int | None = None
    tool_fingerprint: str | None = None
    extra: dict[str, str] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class ParsedReport:
    """A parsed report file. ``tool`` is known even when ``findings`` is empty (a clean run)."""

    format: str
    tool: str
    findings: tuple[RawFinding, ...] = ()
    tool_version: str | None = None


@dataclass(frozen=True)
class Team:
    id: int
    slug: str
    name: str
    email: str


@dataclass(frozen=True)
class Repo:
    id: int
    name: str
    full_name: str
    url: str
    default_branch: str
    team_id: int


@dataclass(frozen=True)
class Run:
    id: int
    repo_id: int
    branch: str
    commit_sha: str
    tool: str
    source_name: str
    source_sha256: str
    ingested_at: datetime
    raw_count: int = 0
    new_count: int = 0
    reopened_count: int = 0
    fixed_count: int = 0


@dataclass(frozen=True)
class Finding:
    id: int
    repo_id: int
    branch: str
    tool: str
    rule_id: str
    fingerprint: str
    fingerprint_version: int
    issue_key: str | None
    message: str
    severity: Severity
    tool_severity: str
    cwe: int | None
    location: Location
    status: Status
    triage: Triage
    triage_note: str | None
    triaged_by: str | None
    triaged_at: datetime | None
    suppressed: bool
    suppression_reason: str | None
    team_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime
    fixed_at: datetime | None
    due_at: datetime | None
    first_run_id: int
    last_run_id: int

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


@dataclass(frozen=True)
class FindingEvent:
    id: int
    finding_id: int
    run_id: int | None
    kind: str
    from_value: str | None
    to_value: str | None
    actor: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class IngestResult:
    run_id: int
    repo: str
    branch: str
    tool: str
    raw_count: int
    new_count: int = 0
    reopened_count: int = 0
    fixed_count: int = 0
    unchanged_count: int = 0
    merged_count: int = 0
    suppressed_count: int = 0


def as_dict(obj: Any) -> Any:
    """JSON-ready copy of a dataclass (nested), with datetimes as ISO UTC text and enums as values."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: as_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, datetime):
        return isoformat(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (list, tuple)):
        return [as_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {key: as_dict(value) for key, value in obj.items()}
    return obj
