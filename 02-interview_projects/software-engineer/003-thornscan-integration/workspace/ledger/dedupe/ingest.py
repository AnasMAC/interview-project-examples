"""The ingest pipeline: one report file -> one ``runs`` row and its findings.

The only entry point the API and the CLI use. Runs inside the caller's
transaction and never commits; everything that can reject the file (inputs,
parsing, duplicate upload, a broken baseline or OWNERS file) is checked
before the first write.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

from ledger.core import clock, log
from ledger.core import repo as rows
from ledger.core.config import Settings
from ledger.core.errors import Conflict, InvalidInput
from ledger.core.models import IngestResult, Repo
from ledger.dedupe.baseline import load_baseline
from ledger.dedupe.lifecycle import apply_run
from ledger.normalize.finding import normalize

BASELINE_FILE = ".ledger-baseline.json"
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_SAME_FILE = (
    "SELECT id FROM runs WHERE repo_id = ? AND branch = ? AND commit_sha = ? AND tool = ? AND source_sha256 = ?"
)
_log = log.get_logger("dedupe.ingest")


def baseline_path(settings: Settings, repo: Repo) -> Path:
    return settings.samples_dir / "repos" / repo.name / BASELINE_FILE


def ingest_report(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    repo: Repo,
    branch: str,
    commit_sha: str,
    data: bytes,
    source: str,
    fmt: str | None = None,
) -> IngestResult:
    """Parse ``data`` and apply it as one run of its tool on ``repo``/``branch``."""
    from ledger.ownership.owners import load_owners
    from ledger.ownership.teams import owners_path
    from ledger.parsers.registry import parse_report
    from ledger.sla.calendar import load_calendar
    from ledger.sla.policy import load_policy

    branch, commit = branch.strip(), commit_sha.strip().lower()
    if not branch:
        raise InvalidInput("branch must not be empty", field="branch")
    if _COMMIT.fullmatch(commit) is None:
        raise InvalidInput(f"commit must be 7-40 hex characters, got {commit_sha!r}", field="commit")

    report = parse_report(data, source=source, fmt=fmt)
    digest = hashlib.sha256(data).hexdigest()
    previous = rows.fetch_one(conn, _SAME_FILE, [repo.id, branch, commit, report.tool, digest])
    if previous is not None:
        raise Conflict(
            f"{source} was already ingested for {repo.name} {branch}@{commit[:10]} (run {previous['id']})",
            run_id=previous["id"],
        )
    baseline = load_baseline(baseline_path(settings, repo))
    owners = load_owners(owners_path(settings, repo))
    policy = load_policy(settings.sla_policy_path)
    calendar = load_calendar(settings.holidays_path, settings.timezone)

    run = {"repo_id": repo.id, "branch": branch, "commit_sha": commit, "tool": report.tool, "source_name": source,
           "source_sha256": digest, "ingested_at": clock.now()}
    run_id = rows.insert(conn, "runs", run)
    findings = [normalize(raw, repo=repo) for raw in report.findings]
    result = apply_run(
        conn, rows.get_run(conn, run_id), findings,
        repo=repo, baseline=baseline, owners=owners, policy=policy, calendar=calendar,
    )
    counts = {"raw": result.raw_count, "new": result.new_count, "reopened": result.reopened_count,
              "fixed": result.fixed_count, "merged": result.merged_count, "suppressed": result.suppressed_count}
    _log.info("ingest.done", extra={"run_id": run_id, "repo": repo.name, "branch": branch, "tool": report.tool,
                                    "source": source, **counts})
    return result
