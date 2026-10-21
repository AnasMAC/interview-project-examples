"""Shared test fixtures: a migrated temp database, a frozen clock and row factories.

Every ``LedgerTestCase`` gets its own temporary directory and SQLite file, so
test modules can run in parallel processes without touching ``var/``.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ledger.core import clock, db, migrations, repo
from ledger.core.config import DEFAULT_CONFIG, Settings, load_settings
from ledger.core.models import Finding, Location, RawFinding, Repo, Run, Severity, Team

# World "today": 2026-09-23 14:00 Europe/Berlin (+02:00).
TODAY = datetime(2026, 9, 23, 12, 0, tzinfo=clock.UTC)

_seq = itertools.count(1)


def make_settings(directory: Path, **overrides: Any) -> Settings:
    """The checked-in config with the database moved to ``directory``; ignores the real environment."""
    settings = load_settings(DEFAULT_CONFIG, env={"LEDGER_DB": str(Path(directory) / "ledger.db")})
    return replace(settings, **overrides)


class LedgerTestCase(unittest.TestCase):
    """``self.conn`` (migrated), ``self.settings``, ``self.tmp`` and ``self.clock`` frozen at ``TODAY``."""

    def setUp(self) -> None:
        super().setUp()
        tmp = tempfile.TemporaryDirectory(prefix="ledger-test-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.settings = make_settings(self.tmp)
        self.clock = self.enterContext(clock.frozen(TODAY))
        self.conn = db.open_db(self.settings)
        self.addCleanup(self.conn.close)
        migrations.migrate(self.conn)


def make_team(conn: Any, slug: str | None = None, **fields: Any) -> Team:
    slug = slug or f"team-{next(_seq)}"
    name = slug.replace("-", " ").title()
    values = {"slug": slug, "name": name, "email": f"{slug}-team@fernwick.example.test", **fields}
    return repo.get_team(conn, repo.insert(conn, "teams", values))


def make_repo(conn: Any, name: str | None = None, *, team: Team | None = None, **fields: Any) -> Repo:
    team = team or make_team(conn)
    name = name or f"service-{next(_seq)}"
    values = {
        "name": name,
        "full_name": f"{team.slug}/{name}",
        "url": f"https://git.fernwick.example.test/{team.slug}/{name}",
        "default_branch": "main",
        "team_id": team.id,
        **fields,
    }
    return repo.get_repo(conn, repo.insert(conn, "repos", values))


def make_run(conn: Any, repository: Repo | None = None, **fields: Any) -> Run:
    repository = repository or make_repo(conn)
    n = next(_seq)
    values = {
        "repo_id": repository.id,
        "branch": repository.default_branch,
        "commit_sha": hashlib.sha1(f"commit-{n}".encode()).hexdigest(),
        "tool": "brackish",
        "source_name": f"brackish-{n}.sarif",
        "source_sha256": hashlib.sha256(f"report-{n}".encode()).hexdigest(),
        "ingested_at": clock.now(),
        **fields,
    }
    return repo.get_run(conn, repo.insert(conn, "runs", values))


def make_finding(conn: Any, run: Run | None = None, *, location: Location | None = None, **fields: Any) -> Finding:
    """An open (``new``) medium SAST finding first seen in ``run``; any column can be overridden."""
    run = run or make_run(conn)
    n = next(_seq)
    seen = run.ingested_at
    values = {
        "repo_id": run.repo_id,
        "branch": run.branch,
        "tool": run.tool,
        "rule_id": f"BRK-{n:04d}",
        "fingerprint": hashlib.sha256(f"finding-{n}".encode()).hexdigest(),
        "message": f"Example finding {n}",
        "severity": Severity.MEDIUM,
        "tool_severity": "warning",
        **repo.location_columns(location or Location.code(f"src/module_{n}.py", 10 + n, 5)),
        "team_id": repo.get_repo(conn, run.repo_id).team_id,
        "first_seen_at": seen,
        "last_seen_at": seen,
        "due_at": seen + timedelta(days=42),
        "first_run_id": run.id,
        "last_run_id": run.id,
        **fields,
    }
    return repo.get_finding(conn, repo.insert(conn, "findings", values))


def raw_finding(**fields: Any) -> RawFinding:
    values: dict[str, Any] = {
        "tool": "brackish",
        "rule_id": "BRK-SQLI-001",
        "severity": "error",
        "location": Location.code("src/payments/refunds.py", 42, 9),
        "message": "SQL query built from request data",
        "cwe": 89,
        **fields,
    }
    return RawFinding(**values)


def sarif_report(*results: tuple[str, int], tool: str = "Brackish", rule: str = "BRK-SQLI-001", cwe: int = 89) -> bytes:
    """A minimal SARIF 2.1.0 log with one ``error`` result per ``(path, line)``, for tests of the real pipeline."""
    found = [
        {"ruleId": rule, "level": "error", "message": {"text": f"{rule} at {path}:{line}"},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": path}, "region": {"startLine": line}}}]}
        for path, line in results
    ]  # fmt: skip
    driver = {"name": tool, "semanticVersion": "5.1.0", "rules": [{"id": rule, "properties": {"cwe": f"CWE-{cwe}"}}]}
    return json.dumps({"version": "2.1.0", "runs": [{"tool": {"driver": driver}, "results": found}]}).encode()
