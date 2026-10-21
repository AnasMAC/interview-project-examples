"""Baseline suppressions: ``.ledger-baseline.json`` kept in each repository (ADR 0003).

::

    {"version": 1, "suppressions": [
        {"tool": "brackish", "rule": "BRK-SECRET-004", "path": "tests/fixtures/**",
         "reason": "Fake keys used by unit tests", "expires": "2026-12-31",
         "ticket": "SEC-214", "added_by": "mrojas"}]}

An entry matches when every criterion it sets matches (``tool``, ``rule``
and ``fingerprint`` exactly, ``path`` as a glob on the repo-relative path,
always anchored at the repo root) and it has not expired (``expires`` is the
last valid day, UTC). At least one of ``rule``, ``path`` or ``fingerprint`` is
required, so a typo cannot suppress a whole tool. The first match wins.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path
from typing import Any

from ledger.core import clock
from ledger.core.errors import ParseError
from ledger.dedupe.fingerprint import fingerprint
from ledger.normalize.finding import NormalizedFinding

_KEYS = {"tool", "rule", "path", "fingerprint", "reason", "expires", "ticket", "added_by"}


@dataclass(frozen=True)
class BaselineEntry:
    reason: str
    tool: str | None = None
    rule: str | None = None
    path: str | None = None
    fingerprint: str | None = None
    expires: date | None = None
    ticket: str | None = None
    added_by: str | None = None

    @cached_property
    def path_pattern(self) -> re.Pattern[str] | None:
        return None if self.path is None else glob_to_regex(self.path)

    def matches(self, finding: NormalizedFinding, fingerprint: str, today: date) -> bool:
        raw = finding.raw
        if self.expires is not None and today > self.expires:
            return False
        if self.tool is not None and self.tool != raw.tool:
            return False
        if self.rule is not None and self.rule != raw.rule_id:
            return False
        if self.fingerprint is not None and self.fingerprint != fingerprint:
            return False
        if self.path_pattern is not None:
            return finding.location.path is not None and self.path_pattern.fullmatch(finding.location.path) is not None
        return True


@dataclass(frozen=True)
class Baseline:
    entries: tuple[BaselineEntry, ...] = ()

    def match(self, finding: NormalizedFinding) -> BaselineEntry | None:
        if not self.entries:
            return None
        value, today = fingerprint(finding), clock.now().date()
        return next((entry for entry in self.entries if entry.matches(finding, value, today)), None)


def load_baseline(path: Path) -> Baseline:
    """Read a baseline file; a missing file is an empty baseline, a malformed one a ParseError."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Baseline()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError(f"{path}: not valid JSON: {exc}", source=str(path)) from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("suppressions"), list):
        raise ParseError(f"{path}: expected {{'version': 1, 'suppressions': [...]}}", source=str(path))
    return Baseline(tuple(_entry(item, path, index) for index, item in enumerate(data["suppressions"])))


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """``*`` within a segment, ``**`` across segments, a trailing ``/`` matches everything below."""
    if pattern.endswith("/"):
        pattern += "**"
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", pattern.lstrip("/"))
    tokens = {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    return re.compile("".join(tokens.get(part, re.escape(part)) for part in parts))


def _entry(item: Any, path: Path, index: int) -> BaselineEntry:
    def fail(problem: str) -> ParseError:
        return ParseError(f"{path}: suppressions[{index}]: {problem}", source=str(path), entry=index)

    if not isinstance(item, dict):
        raise fail("must be an object")
    unknown = sorted(set(item) - _KEYS)
    if unknown:
        raise fail(f"unknown keys {', '.join(unknown)}")
    if any(not isinstance(value, str) or not value.strip() for value in item.values()):
        raise fail("values must be non-empty strings")
    if "reason" not in item:
        raise fail("a reason is required")
    if not {"rule", "path", "fingerprint"} & set(item):
        raise fail("needs at least one of rule, path, fingerprint")
    try:
        expires = date.fromisoformat(item["expires"]) if "expires" in item else None
    except ValueError as exc:
        raise fail(f"expires must be YYYY-MM-DD, got {item['expires']!r}") from exc
    return BaselineEntry(**{**item, "expires": expires})
