"""Weekly report as a standalone HTML page (mailed to engineering managers on Mondays).

Messages, paths and URLs come straight from scanner output and pentest
reports, so every value goes through ``html.escape`` before it reaches the
page. The templates themselves contain no data.
"""

from __future__ import annotations

import html
from string import Template

from ledger.reports import tables
from ledger.reports.weekly import TeamWeek, WeeklyReport

_PAGE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>$title</title>
<style>
body { font-family: sans-serif; margin: 2em; color: #222; } .meta { color: #666; }
table { border-collapse: collapse; margin: 0.5em 0 1.5em; } th { background: #f2f2f2; }
th, td { border: 1px solid #ccc; padding: 0.25em 0.6em; text-align: left; }
</style>
</head>
<body>
<h1>$title</h1>
<p class="meta">$intro</p>
<h2>Summary</h2>
$summary
$teams
</body>
</html>
"""
)

_TEAM = Template(
    """<section id="team-$slug">
<h2>$name</h2>
<p>New this week: $opened, fixed: $fixed, reopened: $reopened. Open: $open_total.</p>
$severities
<h3>SLA breaches ($breach_count)</h3>
$breaches
<h3>Oldest open findings</h3>
$oldest
</section>
"""
)


def render_html(report: WeeklyReport) -> str:
    return _PAGE.substitute(
        title=_esc(tables.title(report)),
        intro=_esc(tables.intro(report)),
        summary=_table(tables.SUMMARY_HEADERS, tables.summary_rows(report)),
        teams="\n".join(_team(tw, report) for tw in report.teams),
    )


def _team(tw: TeamWeek, report: WeeklyReport) -> str:
    breaches = _table(tables.BREACH_HEADERS, tables.breach_rows(tw, report)) if tw.breaches else "<p>None.</p>"
    if tables.more_breaches(tw):
        breaches += f"\n<p>... and {tables.more_breaches(tw)} more.</p>"
    oldest = _table(tables.OLDEST_HEADERS, tables.oldest_rows(tw, report)) if tw.oldest_open else "<p>None.</p>"
    return _TEAM.substitute(
        slug=_esc(tw.team.slug),
        name=_esc(tw.team.name),
        opened=tw.opened,
        fixed=tw.fixed,
        reopened=tw.reopened,
        open_total=tw.open_total,
        severities=_table(tables.SEVERITY_HEADERS, [tables.severity_row(tw)]),
        breach_count=len(tw.breaches),
        breaches=breaches,
        oldest=oldest,
    )


def _table(headers: tuple[str, ...], rows: list[tables.Row]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "\n".join("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in row) + "</tr>" for row in rows)
    return f"<table>\n<thead><tr>{head}</tr></thead>\n<tbody>\n{body}\n</tbody>\n</table>"


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)
