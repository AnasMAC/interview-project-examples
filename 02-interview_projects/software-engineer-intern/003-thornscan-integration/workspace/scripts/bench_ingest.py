"""Time ingest of the sample manifest and the weekly report on a large seeded database.

    python3 scripts/bench_ingest.py [--scale 17] [--week 2026-09-21]

Everything runs in throw-away databases in a temporary directory; var/ is not
touched. The clock is frozen at the seed anchor (2026-09-23 14:00 Leipzig) so
breach counts and ages are the same on every run. Numbers go in the PR
description of any change to ingest, dedupe or reports (`make bench`).
"""

from __future__ import annotations

import argparse
import io
import platform
import sqlite3
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ledger.cli import load_manifest  # noqa: E402
from ledger.core import clock, db, migrations, repo  # noqa: E402
from ledger.core.config import DEFAULT_CONFIG, Settings, load_settings  # noqa: E402
from ledger.dedupe.ingest import ingest_report  # noqa: E402
from ledger.reports.csv_export import export_findings_csv  # noqa: E402
from ledger.reports.html import render_html  # noqa: E402
from ledger.reports.markdown import render_markdown  # noqa: E402
from ledger.reports.weekly import build_weekly  # noqa: E402
from ledger.seed import ANCHOR, seed_database  # noqa: E402
from ledger.sla.calendar import load_calendar  # noqa: E402

Step = tuple[str, Any, float]


def timed(steps: list[Step], label: str, func: Callable[[], Any], rows: Callable[[Any], Any] = lambda r: "") -> Any:
    started = time.perf_counter()
    result = func()
    steps.append((label, rows(result), time.perf_counter() - started))
    return result


def seeded(settings: Settings, name: str, scale: int, steps: list[Step]) -> sqlite3.Connection:
    conn = db.connect(settings.db_path.with_name(name))
    migrations.migrate(conn)
    with db.transaction(conn):
        timed(steps, f"seed, scale {scale}", lambda: seed_database(conn, scale=scale), lambda c: c["findings"])
    return conn


def ingest_manifest(conn: sqlite3.Connection, settings: Settings) -> int:
    raw = 0
    for job in load_manifest(settings.samples_dir / "manifest.json"):
        with db.transaction(conn):
            raw += ingest_report(conn, settings, repo=repo.repo_by_name(conn, job.repo), branch=job.branch,
                                 commit_sha=job.commit, data=job.path.read_bytes(), source=job.path.name,
                                 fmt=job.fmt).raw_count  # fmt: skip
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scale", type=int, default=17, help="seed scale for the report steps (17 = ~51k findings)")
    parser.add_argument("--week", type=date.fromisoformat, default=date(2026, 9, 21), help="report week (Monday)")
    args = parser.parse_args(argv)

    steps: list[Step] = []
    with tempfile.TemporaryDirectory(prefix="ledger-bench-") as tmp, clock.frozen(ANCHOR):
        settings = load_settings(DEFAULT_CONFIG, env={"LEDGER_DB": str(Path(tmp) / "small.db")})
        calendar = load_calendar(settings.holidays_path, settings.timezone)

        small = seeded(settings, "small.db", 1, steps)
        files = len(load_manifest(settings.samples_dir / "manifest.json"))
        timed(steps, f"ingest manifest ({files} files)", lambda: ingest_manifest(small, settings), lambda n: n)
        small.close()

        big = seeded(settings, "big.db", args.scale, steps)
        report = timed(steps, "weekly report, all teams", lambda: build_weekly(big, week_start=args.week,
                       calendar=calendar), lambda r: sum(tw.open_total for tw in r.teams))  # fmt: skip
        timed(steps, "render markdown", lambda: render_markdown(report), len)
        timed(steps, "render html", lambda: render_html(report), len)
        timed(steps, "csv export, all findings", lambda: export_findings_csv(big, io.StringIO()), lambda n: n)
        big.close()

    print(f"Ledger bench: Python {platform.python_version()}, SQLite {sqlite3.sqlite_version}, scale {args.scale}")
    print(f"{'step':<34}{'rows':>10}{'seconds':>10}")
    for label, rows, seconds in steps:
        print(f"{label:<34}{rows!s:>10}{seconds:>10.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
