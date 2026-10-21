"""Stand-ins for the parsers, ownership and sla contracts used by dedupe.

Dedupe imports those packages at call time, so the tests swap in these
modules and check dedupe's own behaviour: *when* a due date or an owning team
is computed, not the business calendar or the OWNERS glob rules.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest import mock

from ledger.core import repo as rows
from ledger.core.errors import ParseError
from ledger.core.models import ParsedReport, RawFinding
from ledger.dedupe.baseline import Baseline
from ledger.dedupe.lifecycle import apply_run
from ledger.normalize.finding import normalize
from tests.helpers import LedgerTestCase, make_repo, make_run, make_team

SLA_DAYS = {"critical": 3, "high": 10, "medium": 30, "low": 60}  # calendar days here


def fake_due_at(severity: Any, opened_at: Any, *, policy: Any, calendar: Any) -> Any:
    days = SLA_DAYS.get(severity.value)
    return None if days is None else opened_at + timedelta(days=days)


def fake_resolve_team_id(conn: Any, repo: Any, location: Any, owners: dict[str, int] | None) -> int:
    """``owners`` is ``{path prefix: team id}``."""
    for prefix, team_id in (owners or {}).items():
        if location.path and location.path.startswith(prefix):
            return team_id
    return repo.team_id


class FakeParsers:
    def __init__(self) -> None:
        self.reports: dict[bytes, ParsedReport] = {}

    def add(self, data: bytes, tool: str, *findings: RawFinding) -> bytes:
        self.reports[data] = ParsedReport(format="fake", tool=tool, findings=findings)
        return data

    def parse_report(self, data: bytes, *, source: str, fmt: str | None = None) -> ParsedReport:
        if data not in self.reports:
            raise ParseError(f"{source}: not a report", source=source, line=1)
        return self.reports[data]


@contextmanager
def fake_services(parsers: FakeParsers, owners: dict[str, int] | None = None) -> Iterator[None]:
    modules = {
        "ledger.parsers.registry": SimpleNamespace(parse_report=parsers.parse_report),
        "ledger.ownership.owners": SimpleNamespace(load_owners=lambda path: owners),
        "ledger.ownership.teams": SimpleNamespace(
            resolve_team_id=fake_resolve_team_id, owners_path=lambda settings, repo: settings.samples_dir / "OWNERS"
        ),
        "ledger.sla.policy": SimpleNamespace(due_at=fake_due_at, load_policy=lambda path: "policy"),
        "ledger.sla.calendar": SimpleNamespace(load_calendar=lambda path, tz_name: "calendar"),
    }
    with mock.patch.dict(sys.modules, modules):
        yield


class DedupeTestCase(LedgerTestCase):
    """A ``checkout-api`` repo owned by Payments and ``scan()`` to apply one run of a tool."""

    def setUp(self) -> None:
        super().setUp()
        self.parsers = FakeParsers()
        self.enterContext(fake_services(self.parsers))
        self.team = make_team(self.conn, "payments")
        self.repo = make_repo(self.conn, "checkout-api", team=self.team)

    def scan(self, tool: str, *raws: RawFinding, branch: str = "main", baseline: Baseline | None = None,
             owners: dict[str, int] | None = None):
        run = make_run(self.conn, self.repo, tool=tool, branch=branch)
        findings = [normalize(raw, repo=self.repo) for raw in raws]
        return apply_run(self.conn, run, findings, repo=self.repo, baseline=baseline or Baseline(), owners=owners,
                         policy="policy", calendar="calendar")

    def findings(self, branch: str = "main"):
        result = rows.fetch_all(self.conn, "SELECT id FROM findings WHERE branch = ? ORDER BY id", [branch])
        return [rows.get_finding(self.conn, row["id"]) for row in result]

    def only(self, branch: str = "main"):
        (finding,) = self.findings(branch)
        return finding

    def events(self, finding_id: int) -> list[str]:
        return [event.kind for event in rows.finding_events(self.conn, finding_id)]

    def occurrence_tools(self, finding_id: int) -> list[str]:
        sql = "SELECT tool FROM occurrences WHERE finding_id = ? ORDER BY id"
        return [row["tool"] for row in rows.fetch_all(self.conn, sql, [finding_id])]
