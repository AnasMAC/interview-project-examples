"""Command line: ``python3 -m ledger <command>`` (docs/architecture.md §7).

Exit codes: 0 ok; 1 command-level failure (SLA breaches, a report file that
failed to ingest); 2 usage error or any ``LedgerError``.

``ingest --manifest PATH`` reads a JSON manifest, either a list or an object
with a ``runs`` list, whose entries are ingested in order::

    {"runs": [{"file": "brackish/checkout-api/run-01.sarif", "repo": "checkout-api",
               "branch": "main", "commit": "4be1f0c9d2", "format": "sarif"}]}

``file`` is relative to the manifest's directory; ``format`` is optional.
Every file is its own transaction: a failure is reported and the remaining
files are still ingested.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import json
import os
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ledger import __version__
from ledger.api import findings as finding_queries
from ledger.core import clock, db, log, migrations, repo
from ledger.core.config import Settings, get_settings
from ledger.core.errors import InvalidInput, LedgerError, MigrationError, NotFound
from ledger.core.models import Location, LocationKind, Severity, Status, Triage, as_dict

logger = log.get_logger("cli")


@dataclass(frozen=True)
class IngestJob:
    path: Path
    repo: str
    branch: str
    commit: str
    fmt: str | None


def cmd_migrate(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    done = migrations.migrate(conn)
    for migration in done:
        print(f"applied {migration.version:04d}_{migration.name}")
    print(f"schema version {migrations.current_version(conn)} ({settings.db_path})")
    return 0


def cmd_seed(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    from ledger.seed import seed_database

    if args.scale < 1:
        raise InvalidInput("--scale must be at least 1")
    with db.transaction(conn):
        counts = seed_database(conn, scale=args.scale, seed=args.seed, reset=args.reset)
    print(", ".join(f"{table}: {count}" for table, count in counts.items()))
    return 0


def cmd_ingest(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    from ledger.dedupe.ingest import ingest_report

    if args.manifest:
        if args.files or args.repo or args.branch or args.commit or args.format:
            raise InvalidInput("--manifest cannot be combined with files, --repo, --branch, --commit or --format")
        jobs = load_manifest(Path(args.manifest))
    else:
        missing = [flag for flag in ("repo", "branch", "commit") if not getattr(args, flag)]
        if missing or not args.files:
            raise InvalidInput("ingest needs --repo, --branch, --commit and at least one FILE (or --manifest)")
        if repo.repo_by_name(conn, args.repo) is None:
            raise NotFound(f"unknown repo {args.repo!r}", repo=args.repo)
        jobs = [IngestJob(Path(name), args.repo, args.branch, args.commit, args.format) for name in args.files]

    failed = 0
    for job in jobs:
        try:
            repository = repo.repo_by_name(conn, job.repo)
            if repository is None:
                raise NotFound(f"unknown repo {job.repo!r}", repo=job.repo)
            try:
                data = job.path.read_bytes()
            except OSError as exc:
                raise InvalidInput(f"cannot read {job.path}: {exc.strerror}") from exc
            with db.transaction(conn):
                result = ingest_report(
                    conn, settings, repo=repository, branch=job.branch, commit_sha=job.commit,
                    data=data, source=job.path.name, fmt=job.fmt,
                )
        except LedgerError as exc:
            failed += 1
            print(f"FAIL {job.path}: {exc.message}", file=sys.stderr)
            logger.warning("ingest.failed", extra={"file": str(job.path), "error": exc.code})
            continue
        print(
            f"ok   {result.repo}@{result.branch} {result.tool} run {result.run_id}: {result.raw_count} raw, "
            f"{result.new_count} new, {result.reopened_count} reopened, {result.fixed_count} fixed, "
            f"{result.merged_count} merged, {result.suppressed_count} suppressed  ({job.path})"
        )
    print(f"ingested {len(jobs) - failed} of {len(jobs)} file(s)")
    return 1 if failed else 0


def load_manifest(path: Path) -> list[IngestJob]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InvalidInput(f"cannot read manifest {path}: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise InvalidInput(f"manifest {path} is not valid JSON: {exc}") from exc
    entries = data.get("runs") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise InvalidInput(f"manifest {path} must be a list or an object with a 'runs' list")
    jobs = []
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k] for k in ("file", "repo", "branch", "commit")):
            raise InvalidInput(f"manifest {path} entry {number}: needs string file, repo, branch and commit", entry=number)
        jobs.append(IngestJob(path.parent / entry["file"], entry["repo"], entry["branch"], entry["commit"], entry.get("format")))
    return jobs


def cmd_findings(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    if args.limit < 1:
        raise InvalidInput("--limit must be at least 1")
    filters = {"repo": args.repo, "team": args.team, "severity": args.severity, "status": args.status}
    items, total = finding_queries.search(conn, {k: v or [] for k, v in filters.items()}, limit=args.limit)
    if args.json:
        print(json.dumps({"items": items, "total": total, "limit": args.limit, "offset": 0}, indent=2, ensure_ascii=False))
        return 0
    rows = [("ID", "SEVERITY", "STATUS", "TRIAGE", "REPO", "BRANCH", "TOOL", "LOCATION", "RULE")]
    for item in items:
        location = Location(**{**item["location"], "kind": LocationKind(item["location"]["kind"])})
        rows.append((str(item["id"]), item["severity"], item["status"], item["triage"], item["repo"],
                     item["branch"], item["tool"], location.display(), item["rule_id"]))
    _table(rows)
    print(f"{len(items)} of {total} finding(s)")
    return 0


def cmd_triage(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    with db.transaction(conn):
        finding = finding_queries.set_triage(conn, args.id, args.set, note=args.note, actor=args.actor or _user())
    print(f"finding {finding['id']} triage={finding['triage']} by {finding['triaged_by']}")
    return 0


def cmd_report(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    team_id = _team_id(conn, args.team)
    if args.format == "csv":
        from ledger.reports.csv_export import export_findings_csv

        with _output(args.out, newline="") as out:
            rows = export_findings_csv(conn, out, team_id=team_id)
        print(f"wrote {rows} row(s)" + (f" to {args.out}" if args.out else ""), file=sys.stderr)
        return 0
    if args.week is None:
        raise InvalidInput("--week YYYY-MM-DD (a Monday) is required for md and html reports")
    from ledger.reports.weekly import build_weekly
    from ledger.sla.calendar import load_calendar

    calendar = load_calendar(settings.holidays_path, settings.timezone)
    report = build_weekly(conn, week_start=args.week, calendar=calendar, team_id=team_id)
    if args.format == "md":
        from ledger.reports.markdown import render_markdown as render
    else:
        from ledger.reports.html import render_html as render
    with _output(args.out) as out:
        out.write(render(report))
    return 0


def cmd_sla_check(conn: sqlite3.Connection, settings: Settings, args: argparse.Namespace) -> int:
    from ledger.sla.breach import find_breaches
    from ledger.sla.calendar import load_calendar

    calendar = load_calendar(settings.holidays_path, settings.timezone)
    breaches = find_breaches(conn, now=clock.now(), calendar=calendar, team_id=_team_id(conn, args.team))
    repos = {row["id"]: row["name"] for row in repo.fetch_all(conn, "SELECT id, name FROM repos")}
    teams = {row["id"]: row["slug"] for row in repo.fetch_all(conn, "SELECT id, slug FROM teams")}
    if args.json:
        payload = [{**as_dict(b), "repo": repos.get(b.repo_id), "team": teams.get(b.team_id)} for b in breaches]
        print(json.dumps(payload, indent=2))
    else:
        for b in breaches:
            print(f"BREACH finding {b.finding_id} {b.severity.value} {repos.get(b.repo_id)} team={teams.get(b.team_id, '-')} "
                  f"due {clock.isoformat(b.due_at)} ({b.overdue_days} business day(s) overdue)")
        print(f"{len(breaches)} SLA breach(es)" if breaches else "no SLA breaches")
    return 1 if breaches else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ledger", description="Fernwick AppSec findings ledger.")
    parser.add_argument("--version", action="version", version=f"ledger {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("migrate", help="apply pending schema migrations").set_defaults(func=cmd_migrate)

    p = sub.add_parser("seed", help="load the deterministic demo data (one transaction)")
    p.add_argument("--reset", action="store_true", help="delete existing data first")
    p.add_argument("--scale", type=int, default=1, help="multiplier for repos' history (default 1)")
    p.add_argument("--seed", type=int, default=2026, help="random seed (default 2026)")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("ingest", help="ingest scanner report files, one transaction per file")
    p.add_argument("files", nargs="*", metavar="FILE")
    p.add_argument("--repo", help="repository name, e.g. checkout-api")
    p.add_argument("--branch")
    p.add_argument("--commit", help="commit SHA (7-40 hex characters)")
    p.add_argument("--format", help="sarif, kitewatch, depwarden or pentest_csv (default: detect)")
    p.add_argument("--manifest", help="JSON manifest listing files, repos, branches and commits")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("findings", help="list findings (not suppressed), critical first")
    p.add_argument("--repo", action="append", help="repeatable, like the other filters")
    p.add_argument("--team", action="append", metavar="SLUG")
    p.add_argument("--severity", action="append", choices=[s.value for s in Severity])
    p.add_argument("--status", action="append", choices=[s.value for s in Status])
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_findings)

    p = sub.add_parser("triage", help="record a triage decision")
    p.add_argument("id", type=int)
    p.add_argument("--set", required=True, choices=[t.value for t in Triage])
    p.add_argument("--note")
    p.add_argument("--actor", help="recorded in the triage event (default: $USER)")
    p.set_defaults(func=cmd_triage)

    p = sub.add_parser("report", help="weekly team report (md, html) or findings CSV export")
    p.add_argument("--week", type=_monday, metavar="YYYY-MM-DD", help="Monday the week starts on (md, html)")
    p.add_argument("--team", metavar="SLUG")
    p.add_argument("--format", required=True, choices=["md", "html", "csv"])
    p.add_argument("--out", metavar="PATH", help="write to a file instead of stdout")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("sla-check", help="list SLA breaches; exit 1 when there are any")
    p.add_argument("--team", metavar="SLUG")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sla_check)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # --help / --version (0) and usage errors (2)
        return exc.code if isinstance(exc.code, int) else 2
    try:
        settings = get_settings()
        log.configure(settings.log_level, settings.log_format)
        if settings.now is not None:
            clock.use(lambda: settings.now)
        with contextlib.closing(db.open_db(settings)) as conn:
            if args.command != "migrate" and migrations.pending(conn):
                raise MigrationError("the database schema is not up to date; run `ledger migrate` first")
            return args.func(conn, settings, args)
    except LedgerError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2


def _team_id(conn: sqlite3.Connection, slug: str | None) -> int | None:
    if slug is None:
        return None
    team = repo.team_by_slug(conn, slug)
    if team is None:
        raise NotFound(f"unknown team {slug!r}", team=slug)
    return team.id


def _monday(text: str) -> date:
    try:
        day = date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a date: {text!r} (expected YYYY-MM-DD)") from None
    if day.weekday() != 0:
        raise argparse.ArgumentTypeError(f"{text} is a {day:%A}; report weeks start on Monday")
    return day


def _output(path: str | None, newline: str | None = None) -> Any:
    return contextlib.nullcontext(sys.stdout) if path is None else open(path, "w", encoding="utf-8", newline=newline)


def _table(rows: list[tuple[str, ...]]) -> None:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())


def _user() -> str:
    try:
        return os.environ.get("USER") or getpass.getuser()
    except (KeyError, OSError):
        return "cli"
