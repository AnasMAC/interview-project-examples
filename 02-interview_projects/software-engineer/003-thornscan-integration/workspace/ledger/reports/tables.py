"""Table rows shared by the Markdown and HTML renderers, so both show the same columns."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ledger.core import clock
from ledger.core.models import SEVERITY_ORDER, Severity
from ledger.reports.weekly import TeamWeek, WeeklyReport

BREACH_LIMIT = 20
MESSAGE_WIDTH = 80

Row = Sequence[object]

SUMMARY_HEADERS = ("Team", "New", "Fixed", "Reopened", "Open", "Critical", "High", "SLA breaches")
SEVERITY_HEADERS = tuple(s.value.title() for s in SEVERITY_ORDER)
BREACH_HEADERS = ("Finding", "Repo", "Severity", "Due", "Overdue (business days)")
OLDEST_HEADERS = ("Finding", "Repo", "Severity", "Status", "Triage", "Location", "First seen", "Age (days)", "Message")


def title(report: WeeklyReport) -> str:
    return f"Ledger weekly report {report.week_start} to {report.week_end}"


def intro(report: WeeklyReport) -> str:
    return (
        f"Generated {clock.isoformat(report.generated_at)}. New, fixed and reopened count this week;"
        " open findings, SLA breaches and ages are as of generation. Suppressed findings and"
        " false positives are not included."
    )


def summary_rows(report: WeeklyReport) -> list[Row]:
    return [
        (tw.team.name, tw.opened, tw.fixed, tw.reopened, tw.open_total, tw.open_by_severity[Severity.CRITICAL],
         tw.open_by_severity[Severity.HIGH], len(tw.breaches))
        for tw in report.teams
    ]  # fmt: skip


def severity_row(tw: TeamWeek) -> Row:
    return tuple(tw.open_by_severity[s] for s in SEVERITY_ORDER)


def breach_rows(tw: TeamWeek, report: WeeklyReport) -> list[Row]:
    return [
        (f"#{b.finding_id}", report.repo_names.get(b.repo_id, b.repo_id), b.severity, _day(b.due_at), b.overdue_days)
        for b in tw.breaches[:BREACH_LIMIT]
    ]


def oldest_rows(tw: TeamWeek, report: WeeklyReport) -> list[Row]:
    return [
        (f"#{f.id}", report.repo_names.get(f.repo_id, f.repo_id), f.severity, f.status, f.triage.replace("_", " "),
         f.location.display(), _day(f.first_seen_at), (report.generated_at - f.first_seen_at).days,
         _shorten(f.message))
        for f in tw.oldest_open
    ]  # fmt: skip


def more_breaches(tw: TeamWeek) -> int:
    return max(0, len(tw.breaches) - BREACH_LIMIT)


def _day(value: datetime) -> str:
    return clock.isoformat(value)[:10]


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MESSAGE_WIDTH else text[: MESSAGE_WIDTH - 3] + "..."
