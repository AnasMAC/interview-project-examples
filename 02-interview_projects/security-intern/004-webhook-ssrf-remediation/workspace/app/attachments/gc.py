"""Orphan collection for the attachment root.

Two kinds of drift are reported: files with no ``attachments`` row, and rows
whose file is missing. Collection only ever removes files (never rows) and runs
as a dry run unless ``apply=True``; it walks each tenant directory, so it can
run while uploads are in flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Attachment


@dataclass
class GcReport:
    """Result of one collection run."""

    scanned: int = 0
    orphans: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    applied: bool = False


def find_orphan_files(session: Session, *, root: Path | None = None) -> list[Path]:
    """Files under the attachment root that no row references."""
    raise NotImplementedError("app.attachments.gc.find_orphan_files")


def find_missing_files(session: Session) -> list[Attachment]:
    """Rows whose stored file is gone."""
    raise NotImplementedError("app.attachments.gc.find_missing_files")


def collect(session: Session, *, apply: bool = False, root: Path | None = None) -> GcReport:
    """Report (and optionally delete) orphaned attachment files."""
    raise NotImplementedError("app.attachments.gc.collect")
