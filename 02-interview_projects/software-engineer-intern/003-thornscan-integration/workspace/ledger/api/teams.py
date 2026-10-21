"""Per-team summary: open findings by severity and current SLA breaches.

Like reports, the summary leaves out suppressed findings and findings triaged
as ``false_positive``. Breaches come from ``ledger.sla.breach.find_breaches``
so that the API and ``ledger sla-check`` always agree.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from ledger.core import clock, repo
from ledger.core.config import Settings
from ledger.core.models import OPEN_STATUSES, SEVERITY_ORDER


def summary(conn: sqlite3.Connection, settings: Settings) -> list[dict[str, Any]]:
    from ledger.sla.breach import find_breaches
    from ledger.sla.calendar import load_calendar

    statuses = sorted(status.value for status in OPEN_STATUSES)
    rows = repo.fetch_all(
        conn,
        "SELECT f.team_id, f.severity, COUNT(*) AS n FROM findings f "
        f"WHERE f.status IN ({repo.placeholders(statuses)}) AND f.suppressed = 0 AND f.triage != 'false_positive' "
        "GROUP BY f.team_id, f.severity",
        statuses,
    )
    open_counts: dict[int, dict[str, int]] = {}
    for row in rows:
        open_counts.setdefault(row["team_id"], {})[row["severity"]] = row["n"]
    breaches: dict[int | None, int] = {}
    calendar = load_calendar(settings.holidays_path, settings.timezone)
    for breach in find_breaches(conn, now=clock.now(), calendar=calendar):
        breaches[breach.team_id] = breaches.get(breach.team_id, 0) + 1

    items = []
    for team in repo.fetch_all(conn, "SELECT * FROM teams ORDER BY slug"):
        counts = open_counts.get(team["id"], {})
        by_severity = {severity.value: counts.get(severity.value, 0) for severity in SEVERITY_ORDER}
        items.append({
            **dict(team),
            "open": by_severity,
            "open_total": sum(by_severity.values()),
            "breaches": breaches.get(team["id"], 0),
        })
    return items
