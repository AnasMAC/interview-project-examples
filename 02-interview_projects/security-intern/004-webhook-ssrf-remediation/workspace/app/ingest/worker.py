"""Spool loop, per-file outcomes and the parse cache.

One run walks the spool in filename order. For each file:

1. read the bytes and compute ``sha256``;
2. look the ``Message-ID`` up in ``ingest_receipts`` - a duplicate is recorded
   and the file is moved to ``processed``;
3. parse (through the cache, see below), resolve the sender, find or create
   the ticket, store attachments, write the message and record the receipt;
4. move the file to ``processed/<YYYY-MM-DD>/``; on failure move it to
   ``failed/`` and write ``<name>.error.txt`` beside it.

Parse cache: results are stored as **JSON** under ``<spool>/.cache/<sha256>.json``
and only reused when the file's digest still matches the cache entry's; the
JSON is re-validated on load and a malformed entry is ignored. (The cache is
never unpickled: the spool directory is written by whoever drops mail in, so
nothing in it may be trusted as code.)

Every row this worker writes goes through the caller's session in one
transaction per file; a failed file leaves no ticket behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

CACHE_DIR_NAME = ".cache"
EML_SUFFIX = ".eml"
MSG_SUFFIX = ".msg"


@dataclass
class IngestReport:
    """Counters for one worker run."""

    files_seen: int = 0
    processed: int = 0
    tickets_created: int = 0
    replies: int = 0
    duplicates: int = 0
    unsupported: int = 0
    failed: int = 0
    attachments: int = 0
    failures: list[str] = field(default_factory=list)


def collect_spool(spool_dir: Path) -> list[Path]:
    """Every candidate file in the spool, in filename order."""
    raise NotImplementedError("app.ingest.worker.collect_spool")


def cache_path(spool_dir: Path, sha256_hex: str) -> Path:
    """Path of the JSON parse cache entry for a file."""
    raise NotImplementedError("app.ingest.worker.cache_path")


def load_cached(cache_file: Path, *, sha256_hex: str) -> dict | None:
    """Return the cached parse result, or ``None`` when it is absent or stale."""
    raise NotImplementedError("app.ingest.worker.load_cached")


def store_cached(cache_file: Path, payload: dict) -> None:
    """Write a parse result to the cache; the caller passes JSON-safe data."""
    raise NotImplementedError("app.ingest.worker.store_cached")


def move_to_processed(path: Path, processed_dir: Path, *, now=None) -> Path:
    """Move a processed file to ``processed_dir/<YYYY-MM-DD>/``."""
    raise NotImplementedError("app.ingest.worker.move_to_processed")


def move_to_failed(path: Path, failed_dir: Path, error: str) -> Path:
    """Move a failing file to ``failed/`` and write ``<name>.error.txt``."""
    raise NotImplementedError("app.ingest.worker.move_to_failed")


def run_once(
    session: Session,
    *,
    spool_dir: Path,
    processed_dir: Path | None = None,
    failed_dir: Path | None = None,
    limit: int | None = None,
) -> IngestReport:
    """Process the spool once and return the counters."""
    raise NotImplementedError("app.ingest.worker.run_once")
