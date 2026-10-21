"""Schema migrations: ``ledger/migrations/NNNN_name.sql`` applied once each, in numeric order.

Each file runs in its own transaction together with its ``schema_migrations``
row, so a failing file leaves nothing behind. Files must not contain
BEGIN/COMMIT. An applied file must never be edited: its checksum is recorded
and ``migrate()`` refuses to run when it changes. Add a new file instead.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ledger.core import clock
from ledger.core.errors import MigrationError
from ledger.core.log import get_logger

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
log = get_logger("migrations")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: dict[int, Migration] = {}
    for path in directory.glob("*.sql"):
        match = FILENAME.match(path.name)
        if match is None:
            raise MigrationError(f"bad migration file name {path.name!r}, expected NNNN_name.sql", file=path.name)
        version = int(match.group(1))
        if version in found:
            raise MigrationError(f"two migrations share version {version:04d}", file=path.name)
        found[version] = Migration(version, match.group(2), path, hashlib.sha256(path.read_bytes()).hexdigest())
    return [found[version] for version in sorted(found)]


def applied(conn: sqlite3.Connection) -> dict[int, str]:
    """Applied versions mapped to their recorded checksum."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    return {row[0]: row[1] for row in conn.execute("SELECT version, checksum FROM schema_migrations")}


def current_version(conn: sqlite3.Connection) -> int:
    return max(applied(conn), default=0)


def pending(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    done = applied(conn)
    todo = []
    for migration in discover(directory):
        if migration.version not in done:
            todo.append(migration)
        elif done[migration.version] != migration.checksum:
            raise MigrationError(
                f"migration {migration.version:04d}_{migration.name} was edited after it was applied",
                version=migration.version,
            )
    return todo


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR, *, target: int | None = None) -> list[Migration]:
    """Apply pending migrations up to ``target`` (inclusive); returns what was applied."""
    if conn.in_transaction:
        raise MigrationError("migrate() must not run inside an open transaction")
    done = []
    for migration in pending(conn, directory):
        if target is not None and migration.version > target:
            break
        if _apply(conn, migration):
            done.append(migration)
            log.info("migrations.applied", extra={"version": migration.version, "migration": migration.name})
    return done


def _apply(conn: sqlite3.Connection, migration: Migration) -> bool:
    # executescript() commits any open transaction first, so BEGIN/COMMIT live
    # in the script. The bookkeeping row goes first: a concurrent migrator
    # that won the race makes it fail on the primary key before any DDL runs.
    # All interpolated values are validated (int, [a-z0-9_], hex, timestamp).
    script = (
        "BEGIN IMMEDIATE;\n"
        "INSERT INTO schema_migrations (version, name, checksum, applied_at) VALUES "
        f"({migration.version}, '{migration.name}', '{migration.checksum}', '{clock.isoformat(clock.now())}');\n"
        f"{migration.path.read_text(encoding='utf-8')}\n;\nCOMMIT;"
    )
    try:
        conn.executescript(script)
    except sqlite3.Error as exc:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        if applied(conn).get(migration.version) == migration.checksum:
            return False
        raise MigrationError(f"migration {migration.version:04d}_{migration.name} failed: {exc}", version=migration.version) from exc
    return True
