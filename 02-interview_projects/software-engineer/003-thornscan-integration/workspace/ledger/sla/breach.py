"""SLA breaches: open findings whose due date has passed."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ledger.core import clock
from ledger.core.models import OPEN_STATUSES, Severity, Triage
from ledger.core.repo import fetch_all, placeholders
from ledger.sla.calendar import BusinessCalendar

_OPEN = sorted(status.value for status in OPEN_STATUSES)


@dataclass(frozen=True)
class Breach:
    finding_id: int
    repo_id: int
    team_id: int | None
    severity: Severity
    due_at: datetime
    overdue_days: int  # business days past due_at


def find_breaches(
    conn: sqlite3.Connection, *, now: datetime, calendar: BusinessCalendar, team_id: int | None = None
) -> list[Breach]:
    """Open, unsuppressed findings past ``due_at`` (oldest due first), optionally for one team.

    False positives are excluded. Accepted risk still counts: the SLA keeps
    running until risk acceptance gets its own rule (see the Payments request).
    """
    sql = (
        "SELECT id, repo_id, team_id, severity, due_at FROM findings"
        f" WHERE status IN ({placeholders(_OPEN)}) AND suppressed = 0 AND triage <> ?"
        " AND due_at IS NOT NULL AND due_at < ?"
    )
    params: list[object] = [*_OPEN, Triage.FALSE_POSITIVE.value, clock.isoformat(now)]
    if team_id is not None:
        sql += " AND team_id = ?"
        params.append(team_id)
    breaches = []
    for row in fetch_all(conn, sql + " ORDER BY due_at, id", params):
        due = clock.parse_iso(row["due_at"])
        breaches.append(
            Breach(
                finding_id=row["id"],
                repo_id=row["repo_id"],
                team_id=row["team_id"],
                severity=Severity(row["severity"]),
                due_at=due,
                overdue_days=calendar.business_days_between(due, now),
            )
        )
    return breaches
