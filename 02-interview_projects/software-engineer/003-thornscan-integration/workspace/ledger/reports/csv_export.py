"""Findings as CSV for spreadsheets (auditors, team leads planning a sprint).

Scanner messages and pentest titles are attacker-influenced text. A cell that
starts with ``=``, ``+``, ``-``, ``@``, tab or carriage return is run as a
formula by spreadsheet programs, so such cells get a leading ``'``.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Sequence
from typing import TextIO

from ledger.core import repo
from ledger.core.models import Status

COLUMNS = (
    "id", "repo", "branch", "team", "tool", "rule_id", "severity", "tool_severity", "cwe", "status",
    "triage", "location", "message", "first_seen_at", "last_seen_at", "fixed_at", "due_at",
)  # fmt: skip
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def export_findings_csv(
    conn: sqlite3.Connection, out: TextIO, *, team_id: int | None = None, statuses: Sequence[Status] | None = None
) -> int:
    """Write matching findings (suppressed and false positives excluded) ordered by id; returns rows written."""
    where = ["f.suppressed = 0", "f.triage != 'false_positive'"]
    params: list[object] = []
    if team_id is not None:
        where.append("f.team_id = ?")
        params.append(team_id)
    if statuses:
        where.append(f"f.status IN ({repo.placeholders(statuses)})")
        params.extend(Status(s).value for s in statuses)
    sql = (
        "SELECT f.*, r.name AS repo_name, t.slug AS team_slug FROM findings f"
        " JOIN repos r ON r.id = f.repo_id LEFT JOIN teams t ON t.id = f.team_id"
        f" WHERE {' AND '.join(where)} ORDER BY f.id"
    )
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    count = 0
    for count, row in enumerate(conn.execute(sql, params), 1):
        finding = repo.finding_from_row({k: row[k] for k in row.keys() if k not in ("repo_name", "team_slug")})
        writer.writerow(
            _safe(value)
            for value in (
                finding.id, row["repo_name"], finding.branch, row["team_slug"] or "", finding.tool, finding.rule_id,
                finding.severity.value, finding.tool_severity, finding.cwe or "", finding.status.value,
                finding.triage.value, finding.location.display(), finding.message, row["first_seen_at"],
                row["last_seen_at"], row["fixed_at"] or "", row["due_at"] or "",
            )
        )  # fmt: skip
    return count


def _safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
