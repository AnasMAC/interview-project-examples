"""Weekly report as Markdown (pasted into the #appsec-ledger channel and team wikis)."""

from __future__ import annotations

from ledger.reports import tables
from ledger.reports.weekly import TeamWeek, WeeklyReport


def render_markdown(report: WeeklyReport) -> str:
    lines = [f"# {tables.title(report)}", "", tables.intro(report), "", "## Summary", ""]
    lines += _table(tables.SUMMARY_HEADERS, tables.summary_rows(report))
    for tw in report.teams:
        lines += ["", *_team_section(tw, report)]
    return "\n".join(lines) + "\n"


def _team_section(tw: TeamWeek, report: WeeklyReport) -> list[str]:
    summary = f"New this week: {tw.opened}, fixed: {tw.fixed}, reopened: {tw.reopened}. Open: {tw.open_total}."
    lines = [f"## {_cell(tw.team.name)}", "", summary]
    lines += ["", *_table(tables.SEVERITY_HEADERS, [tables.severity_row(tw)])]
    lines += ["", f"### SLA breaches ({len(tw.breaches)})", ""]
    if tw.breaches:
        lines += _table(tables.BREACH_HEADERS, tables.breach_rows(tw, report))
        if tables.more_breaches(tw):
            lines += ["", f"... and {tables.more_breaches(tw)} more (`ledger sla-check --team {tw.team.slug}`)."]
    else:
        lines.append("None.")
    lines += ["", "### Oldest open findings", ""]
    if tw.oldest_open:
        lines += _table(tables.OLDEST_HEADERS, tables.oldest_rows(tw, report))
    else:
        lines.append("None.")
    return lines


def _table(headers: tuple[str, ...], rows: list[tables.Row]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def _cell(value: object) -> str:
    """Keep scanner text inside its table cell: no pipes, line breaks or HTML tags (wikis render those)."""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
