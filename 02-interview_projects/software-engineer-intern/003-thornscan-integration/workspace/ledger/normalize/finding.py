"""A RawFinding with Ledger's severity, a repo-relative location and a CWE number."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ledger.core.models import Location, LocationKind, RawFinding, Repo, Severity
from ledger.normalize.cwe import parse_cwe
from ledger.normalize.paths import normalize_path
from ledger.normalize.severity import normalize_severity


@dataclass(frozen=True)
class NormalizedFinding:
    raw: RawFinding  # unchanged; occurrences store what the tool said
    severity: Severity
    location: Location
    cwe: int | None


def normalize(raw: RawFinding, *, repo: Repo) -> NormalizedFinding:
    location = raw.location
    if location.kind == LocationKind.CODE and location.path:
        location = replace(location, path=normalize_path(location.path, repo=repo))
    cwe = parse_cwe(raw.cwe) if raw.cwe is not None else parse_cwe(raw.extra.get("cwe"))
    return NormalizedFinding(raw=raw, severity=normalize_severity(raw.tool, raw.severity), location=location, cwe=cwe)
