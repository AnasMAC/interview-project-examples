"""Finding lifecycle across runs, per repo and branch (docs/architecture.md §5).

=========== ======================================= ==============================
before      seen in this run                        not seen in a run of its tool
=========== ======================================= ==============================
(none)      insert ``new``, event ``new``, due_at   -
new / open  ``open``, refresh last seen             ``fixed``, event ``fixed``
reopened    stays ``reopened``, refresh             ``fixed``, event ``fixed``
fixed       ``reopened``, due_at from now, event    unchanged
=========== ======================================= ==============================

A sighting is matched to a finding by fingerprint first, then by issue key
against a finding of *another* SAST tool (a merge: the occurrence goes to the
existing finding, which keeps its tool, rule and severity). Only a run of the
finding's own tool can fix it, so a Thistle run never closes a Brackish
finding. Triage columns are never written here.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ledger.core import clock
from ledger.core import repo as rows
from ledger.core.models import OPEN_STATUSES, IngestResult, Repo, Run, Severity, Status
from ledger.dedupe.baseline import Baseline, BaselineEntry
from ledger.dedupe.fingerprint import FINGERPRINT_VERSION, fingerprint
from ledger.dedupe.issue_key import issue_key
from ledger.normalize.finding import NormalizedFinding

if TYPE_CHECKING:
    from ledger.ownership.owners import OwnersFile
    from ledger.sla.calendar import BusinessCalendar
    from ledger.sla.policy import SlaPolicy

_BY_FINGERPRINT = "SELECT * FROM findings WHERE repo_id = ? AND branch = ? AND fingerprint = ?"
_BY_ISSUE_KEY = (
    "SELECT * FROM findings WHERE repo_id = ? AND branch = ? AND issue_key = ? AND tool != ? ORDER BY id LIMIT 1"
)


def apply_run(
    conn: sqlite3.Connection,
    run: Run,
    findings: Sequence[NormalizedFinding],
    *,
    repo: Repo,
    baseline: Baseline,
    owners: OwnersFile | None,
    policy: SlaPolicy,
    calendar: BusinessCalendar,
) -> IngestResult:
    """Record ``findings`` (one run's sightings) and update the run's counters. Does not commit."""
    # Imported at call time so tests can swap these contracts for stand-ins (tests/dedupe/fakes.py).
    from ledger.ownership.teams import resolve_team_id
    from ledger.sla.policy import due_at

    def due(severity: Severity, opened_at: datetime) -> datetime | None:
        return due_at(severity, opened_at, policy=policy, calendar=calendar)

    now = clock.now()
    outcome: dict[int, str] = {}  # finding id -> "new" | "reopened" | "unchanged"
    merged: set[int] = set()
    suppressed: set[int] = set()
    synced: set[int] = set()

    for item in findings:
        raw, entry = item.raw, baseline.match(item)
        fp, key = fingerprint(item), issue_key(item)
        row = rows.fetch_one(conn, _BY_FINGERPRINT, [run.repo_id, run.branch, fp])
        if row is None and key is not None:
            row = rows.fetch_one(conn, _BY_ISSUE_KEY, [run.repo_id, run.branch, key, raw.tool])
            if row is not None:
                merged.add(row["id"])
                _record_merge(conn, row["id"], item, key, run)

        if row is None:
            team_id = resolve_team_id(conn, repo, item.location, owners)
            finding_id = _insert(conn, item, fp, key, entry, run, now, team_id, due(item.severity, now))
            outcome[finding_id] = "new"
            synced.add(finding_id)
            if entry is not None:
                suppressed.add(finding_id)
        else:
            finding_id = row["id"]
            if finding_id not in outcome:
                outcome[finding_id] = _sighted(conn, row, run, now, due)
                if row["suppressed"]:
                    suppressed.add(finding_id)
            # Suppression follows the baseline for the finding's own tool only:
            # an entry written for a Brackish rule says nothing about Thistle's.
            if row["tool"] == raw.tool and finding_id not in synced:
                synced.add(finding_id)
                if _sync_suppression(conn, row, entry, run):
                    suppressed.add(finding_id)
                else:
                    suppressed.discard(finding_id)
        _add_occurrence(conn, finding_id, item, run)

    fixed = _fix_unseen(conn, run, set(outcome), now)
    counts = Counter(outcome.values())
    new, reopened = counts["new"], counts["reopened"]
    totals = {"raw_count": len(findings), "new_count": new, "reopened_count": reopened, "fixed_count": fixed}
    rows.update(conn, "runs", run.id, totals)
    return IngestResult(
        run.id, repo.name, run.branch, run.tool, len(findings), new_count=new, reopened_count=reopened,
        fixed_count=fixed, unchanged_count=counts["unchanged"], merged_count=len(merged),
        suppressed_count=len(suppressed),
    )


def _insert(
    conn: sqlite3.Connection, item: NormalizedFinding, fp: str, key: str | None, entry: BaselineEntry | None,
    run: Run, now: datetime, team_id: int, due: datetime | None,
) -> int:
    raw = item.raw
    finding_id = rows.insert(
        conn,
        "findings",
        {
            "repo_id": run.repo_id,
            "branch": run.branch,
            "tool": raw.tool,
            "rule_id": raw.rule_id,
            "fingerprint": fp,
            "fingerprint_version": FINGERPRINT_VERSION,
            "issue_key": key,
            "message": raw.message,
            "severity": item.severity,
            "tool_severity": raw.severity,
            "cwe": item.cwe,
            **rows.location_columns(item.location),
            "status": Status.NEW,
            "suppressed": entry is not None,
            "suppression_reason": entry.reason if entry else None,
            "team_id": team_id,
            "first_seen_at": now,
            "last_seen_at": now,
            "due_at": due,
            "first_run_id": run.id,
            "last_run_id": run.id,
        },
    )
    rows.add_event(conn, finding_id, "new", run_id=run.id, to_value=Status.NEW.value)
    if entry is not None:
        rows.add_event(conn, finding_id, "suppressed", run_id=run.id, from_value="0", to_value="1", note=entry.reason)
    return finding_id


def _sighted(
    conn: sqlite3.Connection, row: sqlite3.Row, run: Run, now: datetime,
    due: Callable[[Severity, datetime], datetime | None],
) -> str:
    """Refresh an existing finding seen in ``run``; returns ``"reopened"`` or ``"unchanged"``."""
    status = Status(row["status"])
    values: dict[str, Any] = {"last_seen_at": now, "last_run_id": run.id}
    if status == Status.FIXED:
        values.update(status=Status.REOPENED, fixed_at=None, due_at=due(Severity(row["severity"]), now))
    elif status == Status.NEW:
        values["status"] = Status.OPEN
    rows.update(conn, "findings", row["id"], values)
    if status != Status.FIXED:
        return "unchanged"
    rows.add_event(conn, row["id"], "reopened", run_id=run.id, from_value=status.value, to_value=Status.REOPENED.value)
    return "reopened"


def _sync_suppression(conn: sqlite3.Connection, row: sqlite3.Row, entry: BaselineEntry | None, run: Run) -> bool:
    """Make the finding's suppression match the baseline; returns whether it is suppressed now."""
    was, reason = bool(row["suppressed"]), entry.reason if entry else None
    if was == (entry is not None) and row["suppression_reason"] == reason:
        return was
    rows.update(conn, "findings", row["id"], {"suppressed": entry is not None, "suppression_reason": reason})
    if was != (entry is not None):
        kind = "suppressed" if entry is not None else "unsuppressed"
        rows.add_event(conn, row["id"], kind, run_id=run.id, from_value=str(int(was)), to_value=str(int(not was)),
                       note=reason)
    return entry is not None


def _record_merge(conn: sqlite3.Connection, finding_id: int, item: NormalizedFinding, key: str, run: Run) -> None:
    """One ``merged`` event per finding and merging tool, not one per run."""
    sql = "SELECT 1 FROM occurrences WHERE finding_id = ? AND tool = ?"
    if rows.fetch_one(conn, sql, [finding_id, item.raw.tool]) is None:
        source = f"{item.raw.tool}:{item.raw.rule_id}"
        rows.add_event(conn, finding_id, "merged", run_id=run.id, from_value=source, to_value=key)


def _add_occurrence(conn: sqlite3.Connection, finding_id: int, item: NormalizedFinding, run: Run) -> None:
    raw = item.raw
    rows.insert(
        conn,
        "occurrences",
        {
            "finding_id": finding_id,
            "run_id": run.id,
            "tool": raw.tool,
            "rule_id": raw.rule_id,
            "tool_severity": raw.severity,
            "tool_fingerprint": raw.tool_fingerprint,
            "raw_location": raw.location.display(),
            "message": raw.message,
            "evidence": raw.evidence,
        },
    )


def _fix_unseen(conn: sqlite3.Connection, run: Run, seen: set[int], now: datetime) -> int:
    """Close the open findings of ``run``'s tool on its repo and branch that the run did not report."""
    statuses = sorted(status.value for status in OPEN_STATUSES)
    candidates = rows.fetch_all(
        conn,
        f"SELECT id, status FROM findings WHERE repo_id = ? AND branch = ? AND tool = ?"
        f" AND status IN ({rows.placeholders(statuses)}) ORDER BY id",
        [run.repo_id, run.branch, run.tool, *statuses],
    )
    fixed = 0
    for row in candidates:
        if row["id"] in seen:
            continue
        rows.update(conn, "findings", row["id"], {"status": Status.FIXED, "fixed_at": now})
        rows.add_event(conn, row["id"], "fixed", run_id=run.id, from_value=row["status"], to_value=Status.FIXED.value)
        fixed += 1
    return fixed
