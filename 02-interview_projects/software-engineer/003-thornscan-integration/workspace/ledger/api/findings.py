"""Findings queries and triage, shared by the API handlers and ``ledger findings`` / ``ledger triage``.

The functions never begin or commit a transaction; ``set_triage`` must run
inside the caller's ``db.transaction()``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from ledger.core import clock, repo
from ledger.core.errors import InvalidInput
from ledger.core.models import SEVERITY_ORDER, Finding, Severity, Status, Triage, as_dict

# Filter name -> column. Values of the same filter are OR-ed, filters AND-ed.
FILTERS = {
    "repo": "r.name",
    "branch": "f.branch",
    "team": "t.slug",
    "tool": "f.tool",
    "severity": "f.severity",
    "status": "f.status",
    "triage": "f.triage",
}
_ENUMS = {"severity": Severity, "status": Status, "triage": Triage}
_SEVERITY_SORT = "CASE f.severity " + " ".join(f"WHEN '{s.value}' THEN {i}" for i, s in enumerate(SEVERITY_ORDER)) + " END"
_FROM = "FROM findings f JOIN repos r ON r.id = f.repo_id LEFT JOIN teams t ON t.id = f.team_id"
MAX_NOTE = 2000


def serialize(finding: Finding, repo_name: str) -> dict[str, Any]:
    """The API shape of a finding: ``as_dict(finding)`` plus the repo name."""
    return {**as_dict(finding), "repo": repo_name}


def search(
    conn: sqlite3.Connection,
    filters: Mapping[str, Sequence[str]],
    *,
    suppressed: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """One page of findings (critical first, then by id) and the total matching count."""
    where, params = ["f.suppressed = ?"], [int(suppressed)]
    for name, values in filters.items():
        if name not in FILTERS:
            raise InvalidInput(f"unknown filter {name!r}", parameter=name)
        values = [value for value in values if value]
        if not values:
            continue
        if name in _ENUMS:
            allowed = {member.value for member in _ENUMS[name]}
            for value in values:
                if value not in allowed:
                    raise InvalidInput(f"{name} must be one of {', '.join(sorted(allowed))}", parameter=name, value=value)
        where.append(f"{FILTERS[name]} IN ({repo.placeholders(values)})")
        params.extend(values)
    clause = " AND ".join(where)
    total = repo.fetch_one(conn, f"SELECT COUNT(*) {_FROM} WHERE {clause}", params)[0]
    rows = repo.fetch_all(
        conn,
        f"SELECT f.*, r.name AS repo_name {_FROM} WHERE {clause} ORDER BY {_SEVERITY_SORT}, f.id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return [_from_joined(row) for row in rows], int(total)


def detail(conn: sqlite3.Connection, finding_id: int) -> dict[str, Any]:
    """A finding with every occurrence (oldest first, with the run's commit) and its events."""
    finding = repo.get_finding(conn, finding_id)
    occurrences = repo.fetch_all(
        conn,
        "SELECT o.*, r.commit_sha, r.source_name, r.ingested_at FROM occurrences o "
        "JOIN runs r ON r.id = o.run_id WHERE o.finding_id = ? ORDER BY r.ingested_at, o.id",
        [finding_id],
    )
    return {
        **serialize(finding, repo.get_repo(conn, finding.repo_id).name),
        "occurrences": [dict(row) for row in occurrences],
        "events": as_dict(repo.finding_events(conn, finding_id)),
    }


def set_triage(conn: sqlite3.Connection, finding_id: int, triage: str, *, note: str | None, actor: str) -> dict[str, Any]:
    """Set the triage decision and write a ``triage`` event; returns the updated finding."""
    if triage not in {member.value for member in Triage}:
        raise InvalidInput(f"triage must be one of {', '.join(member.value for member in Triage)}", value=triage)
    if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
        raise InvalidInput(f"note must be a string of at most {MAX_NOTE} characters")
    before = repo.get_finding(conn, finding_id)
    now = clock.now()
    repo.update(conn, "findings", finding_id, {"triage": triage, "triage_note": note, "triaged_by": actor, "triaged_at": now})
    repo.add_event(conn, finding_id, "triage", from_value=before.triage.value, to_value=triage, actor=actor, note=note)
    return serialize(repo.get_finding(conn, finding_id), repo.get_repo(conn, before.repo_id).name)


def _from_joined(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    name = data.pop("repo_name")
    return serialize(repo.finding_from_row(data), name)  # type: ignore[arg-type]
