"""Repository helpers: thin SQL wrappers and row -> model mapping. Callers own the transaction."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from ledger.core import clock
from ledger.core.errors import Conflict, NotFound
from ledger.core.models import Finding, FindingEvent, Location, LocationKind, Repo, Run, Severity, Status, Team, Triage

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def to_db(value: Any) -> Any:
    if isinstance(value, datetime):
        return clock.isoformat(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return int(value)
    return value


def placeholders(values: Iterable[Any]) -> str:
    """``"?, ?, ?"`` for an ``IN (...)`` clause; at least one value is required."""
    count = len(list(values))
    if count == 0:
        raise ValueError("placeholders() needs at least one value")
    return ", ".join("?" * count)


def fetch_one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, [to_db(p) for p in params]).fetchone()


def fetch_all(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, [to_db(p) for p in params]).fetchall()


def insert(conn: sqlite3.Connection, table: str, values: Mapping[str, Any]) -> int:
    columns = [_ident(name) for name in values]
    sql = f"INSERT INTO {_ident(table)} ({', '.join(columns)}) VALUES ({placeholders(columns)})"
    try:
        cursor = conn.execute(sql, [to_db(v) for v in values.values()])
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise Conflict(f"{table}: {exc}", table=table) from exc
        raise
    return int(cursor.lastrowid)


def update(conn: sqlite3.Connection, table: str, row_id: int, values: Mapping[str, Any]) -> None:
    assignments = ", ".join(f"{_ident(name)} = ?" for name in values)
    cursor = conn.execute(
        f"UPDATE {_ident(table)} SET {assignments} WHERE id = ?", [*(to_db(v) for v in values.values()), row_id]
    )
    if cursor.rowcount == 0:
        raise NotFound(f"{table} {row_id} not found", table=table, id=row_id)


def get_row(conn: sqlite3.Connection, table: str, row_id: int) -> sqlite3.Row:
    row = fetch_one(conn, f"SELECT * FROM {_ident(table)} WHERE id = ?", [row_id])
    if row is None:
        raise NotFound(f"{table} {row_id} not found", table=table, id=row_id)
    return row


def get_team(conn: sqlite3.Connection, team_id: int) -> Team:
    return Team(**dict(get_row(conn, "teams", team_id)))


def team_by_slug(conn: sqlite3.Connection, slug: str) -> Team | None:
    row = fetch_one(conn, "SELECT * FROM teams WHERE slug = ?", [slug])
    return None if row is None else Team(**dict(row))


def get_repo(conn: sqlite3.Connection, repo_id: int) -> Repo:
    return Repo(**dict(get_row(conn, "repos", repo_id)))


def repo_by_name(conn: sqlite3.Connection, name: str) -> Repo | None:
    row = fetch_one(conn, "SELECT * FROM repos WHERE name = ?", [name])
    return None if row is None else Repo(**dict(row))


def run_from_row(row: sqlite3.Row) -> Run:
    return Run(**{**dict(row), "ingested_at": clock.parse_iso(row["ingested_at"])})


def get_run(conn: sqlite3.Connection, run_id: int) -> Run:
    return run_from_row(get_row(conn, "runs", run_id))


def finding_from_row(row: sqlite3.Row) -> Finding:
    data = dict(row)
    location = Location(
        LocationKind(data.pop("location_kind")),
        path=data.pop("path"),
        line=data.pop("line"),
        column=data.pop("col"),
        url=data.pop("url"),
        parameter=data.pop("parameter"),
        package=data.pop("package"),
        version=data.pop("package_version"),
    )
    for key in ("triaged_at", "first_seen_at", "last_seen_at", "fixed_at", "due_at"):
        data[key] = None if data[key] is None else clock.parse_iso(data[key])
    data.update(
        location=location,
        severity=Severity(data["severity"]),
        status=Status(data["status"]),
        triage=Triage(data["triage"]),
        suppressed=bool(data["suppressed"]),
    )
    return Finding(**data)


def location_columns(location: Location) -> dict[str, Any]:
    """The ``findings`` columns that store a Location (inverse of ``finding_from_row``)."""
    return {
        "location_kind": location.kind,
        "path": location.path,
        "line": location.line,
        "col": location.column,
        "url": location.url,
        "parameter": location.parameter,
        "package": location.package,
        "package_version": location.version,
    }


def get_finding(conn: sqlite3.Connection, finding_id: int) -> Finding:
    return finding_from_row(get_row(conn, "findings", finding_id))


def add_event(
    conn: sqlite3.Connection,
    finding_id: int,
    kind: str,
    *,
    run_id: int | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    actor: str = "ledger",
    note: str | None = None,
) -> int:
    values = {"finding_id": finding_id, "run_id": run_id, "kind": kind, "from_value": from_value, "to_value": to_value}
    return insert(conn, "finding_events", {**values, "actor": actor, "note": note, "created_at": clock.now()})


def finding_events(conn: sqlite3.Connection, finding_id: int) -> list[FindingEvent]:
    rows = fetch_all(conn, "SELECT * FROM finding_events WHERE finding_id = ? ORDER BY created_at, id", [finding_id])
    return [FindingEvent(**{**dict(row), "created_at": clock.parse_iso(row["created_at"])}) for row in rows]


def _ident(name: str) -> str:
    if _IDENT.match(name) is None:
        raise ValueError(f"not a valid SQL identifier: {name!r}")
    return name
