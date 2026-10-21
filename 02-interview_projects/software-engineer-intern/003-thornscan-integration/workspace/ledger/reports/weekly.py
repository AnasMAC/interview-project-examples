"""Weekly team report: what changed in one Monday-Sunday week and what is still open.

Built for the Monday AppSec sync. The week counters (new, fixed, reopened) use
the week's boundaries in the business calendar's time zone (Europe/Berlin);
open counts, SLA breaches and the oldest open findings describe the database
at ``generated_at``. Suppressed findings and false positives are left out
(docs/architecture.md, section 3).

Each team's findings are loaded and walked with their events, using the
same ``core.repo`` helpers as the API. At demo size (8 teams, ~3,000
findings) the whole report takes well under a second.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING

from ledger.core import clock, repo
from ledger.core.models import SEVERITY_ORDER, Finding, Severity, Team

if TYPE_CHECKING:
    from ledger.sla.breach import Breach
    from ledger.sla.calendar import BusinessCalendar

OLDEST_LIMIT = 10


@dataclass(frozen=True)
class TeamWeek:
    team: Team
    opened: int
    fixed: int
    reopened: int
    open_by_severity: dict[Severity, int]
    breaches: tuple[Breach, ...]
    oldest_open: tuple[Finding, ...]

    @property
    def open_total(self) -> int:
        return sum(self.open_by_severity.values())


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    week_end: date
    generated_at: datetime
    teams: tuple[TeamWeek, ...]
    repo_names: dict[int, str] = field(default_factory=dict)  # repo id -> name, for the renderers


def build_weekly(
    conn: sqlite3.Connection, *, week_start: date, calendar: BusinessCalendar, team_id: int | None = None
) -> WeeklyReport:
    """Report for the week containing ``week_start`` (moved back to its Monday)."""
    from ledger.sla.breach import find_breaches

    monday = week_start - timedelta(days=week_start.weekday())
    # Local midnights: the week that ends the summer time is 169 hours long.
    start, end = _local_midnight(monday, calendar), _local_midnight(monday + timedelta(days=7), calendar)
    generated_at = clock.now()
    if team_id is None:
        teams = [Team(**dict(row)) for row in repo.fetch_all(conn, "SELECT * FROM teams ORDER BY id")]
    else:
        teams = [repo.get_team(conn, team_id)]
    weeks = []
    for team in teams:
        breaches = tuple(find_breaches(conn, now=generated_at, calendar=calendar, team_id=team.id))
        weeks.append(_team_week(conn, team, start, end, breaches))
    names = {row["id"]: row["name"] for row in repo.fetch_all(conn, "SELECT id, name FROM repos")}
    return WeeklyReport(monday, monday + timedelta(days=6), generated_at, tuple(weeks), names)


def _team_week(
    conn: sqlite3.Connection, team: Team, start: datetime, end: datetime, breaches: tuple[Breach, ...]
) -> TeamWeek:
    sql = "SELECT * FROM findings WHERE team_id = ? AND suppressed = 0 AND triage != 'false_positive' ORDER BY id"
    rows = repo.fetch_all(conn, sql, [team.id])
    opened = fixed = reopened = 0
    open_by_severity = dict.fromkeys(SEVERITY_ORDER, 0)
    still_open = []
    for finding in map(repo.finding_from_row, rows):
        opened += start <= finding.first_seen_at < end
        kinds = {event.kind for event in repo.finding_events(conn, finding.id) if start <= event.created_at < end}
        fixed += "fixed" in kinds
        reopened += "reopened" in kinds
        if finding.is_open:
            open_by_severity[finding.severity] += 1
            still_open.append(finding)
    still_open.sort(key=lambda f: (f.first_seen_at, f.id))
    return TeamWeek(team, opened, fixed, reopened, open_by_severity, breaches, tuple(still_open[:OLDEST_LIMIT]))


def _local_midnight(day: date, calendar: BusinessCalendar) -> datetime:
    return datetime.combine(day, time(0), tzinfo=calendar.tz).astimezone(clock.UTC)
