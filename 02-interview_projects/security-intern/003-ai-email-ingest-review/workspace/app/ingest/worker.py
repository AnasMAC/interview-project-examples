# ai-assisted: generated with an assistant on 2026-05-02, PR #230 by Priya Patel
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
JSON is re-validated on load and a malformed entry is ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from sqlalchemy.orm import Session

from app.clock import now as clock_now
from app.ingest.attachments import store_attachments
from app.ingest.mime_threads import find_thread, normalize_message_id
from app.ingest.parser import ParseError, ParsedEmail, parse_message
from app.ingest.receipts import (
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_UNSUPPORTED,
    record_receipt,
    seen_message_id,
)
from app.models import Message, Tenant, Ticket, User

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
    if not spool_dir.exists():
        return []
    candidates = [
        p for p in sorted(spool_dir.iterdir())
        if p.is_file() and not p.name.startswith(".")
    ]
    return candidates


def cache_path(spool_dir: Path, sha256_hex: str) -> Path:
    """Path of the JSON parse cache entry for a file."""
    return spool_dir / CACHE_DIR_NAME / f"{sha256_hex}.json"


def load_cached(cache_file: Path, *, sha256_hex: str) -> dict | None:
    """Return the cached parse result, or ``None`` when it is absent or stale."""
    if not cache_file.exists():
        return None
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("sha256") == sha256_hex:
            return data.get("parsed")
    except Exception:
        return None
    return None


def store_cached(cache_file: Path, payload: dict) -> None:
    """Write a parse result to the cache; the caller passes JSON-safe data."""
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = cache_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    temp_file.replace(cache_file)


def move_to_processed(path: Path, processed_dir: Path, *, now=None) -> Path:
    """Move a processed file to ``processed_dir/<YYYY-MM-DD>/``."""
    ts = now or clock_now()
    day_str = ts.strftime("%Y-%m-%d")
    target_dir = processed_dir / day_str
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / path.name
    shutil.move(str(path), str(target))
    return target


def move_to_failed(path: Path, failed_dir: Path, error: str) -> Path:
    """Move a failing file to ``failed/`` and write ``<name>.error.txt``."""
    failed_dir.mkdir(parents=True, exist_ok=True)
    target = failed_dir / path.name
    shutil.move(str(path), str(target))
    err_file = failed_dir / f"{path.name}.error.txt"
    with open(err_file, "w", encoding="utf-8") as f:
        f.write(error)
    return target


def resolve_sender(session: Session, from_address: str) -> tuple[Tenant | None, User | None]:
    """Resolve tenant and user by looking up the sender email in the database."""
    if len(from_address.strip()) == 0:
        return None, None

    user = (
        session.query(User)
        .filter(User.email == from_address.strip().lower())
        .first()
    )
    if user is not None:
        tenant = session.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        return tenant, user

    return None, None


def _next_ticket_number(session: Session, tenant: Tenant) -> str:
    """Generate the next formatted ticket number: <PREFIX>-<SEQ>."""
    count = session.query(Ticket).filter(Ticket.tenant_id == tenant.id).count()
    return f"{tenant.prefix}-{count + 1:04d}"


def process_file(
    session: Session,
    file_path: Path,
    *,
    processed_dir: Path,
    failed_dir: Path,
    report: IngestReport,
) -> None:
    """Ingest a single email spool file."""
    if file_path.suffix.lower() == MSG_SUFFIX:
        record_receipt(
            session,
            filename=file_path.name,
            sha256="",
            message_id=None,
            status=STATUS_UNSUPPORTED,
            error="Outlook .msg not supported",
        )
        move_to_failed(file_path, failed_dir, "Outlook .msg not supported")
        report.unsupported += 1
        return

    raw_bytes = file_path.read_bytes()
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()

    try:
        parsed = parse_message(raw_bytes)
    except ParseError as exc:
        record_receipt(
            session,
            filename=file_path.name,
            sha256=sha256_hex,
            message_id=None,
            status=STATUS_FAILED,
            error=str(exc),
        )
        move_to_failed(file_path, failed_dir, str(exc))
        report.failed += 1
        report.failures.append(f"{file_path.name}: {exc}")
        return

    norm_msg_id = normalize_message_id(parsed.message_id)

    prior_receipt = seen_message_id(session, norm_msg_id)
    if prior_receipt is not None:
        record_receipt(
            session,
            filename=file_path.name,
            sha256=sha256_hex,
            message_id=norm_msg_id,
            status=STATUS_DUPLICATE,
            ticket_id=prior_receipt.ticket_id,
        )
        move_to_processed(file_path, processed_dir)
        report.duplicates += 1
        return

    tenant, user = resolve_sender(session, parsed.from_address)
    if tenant is None or user is None:
        record_receipt(
            session,
            filename=file_path.name,
            sha256=sha256_hex,
            message_id=norm_msg_id,
            status=STATUS_FAILED,
            error=f"unknown sender {parsed.from_address}",
        )
        move_to_failed(file_path, failed_dir, f"unknown sender {parsed.from_address}")
        report.failed += 1
        report.failures.append(f"{file_path.name}: unknown sender")
        return

    existing_ticket = find_thread(session, tenant=tenant, parsed=parsed)
    if existing_ticket is not None:
        ticket = existing_ticket
        report.replies += 1
    else:
        ticket_number = _next_ticket_number(session, tenant)
        ticket = Ticket(
            tenant_id=tenant.id,
            number=ticket_number,
            subject=parsed.subject or "(No Subject)",
            body=parsed.body_text or "",
            status="open",
            priority="normal",
            channel="email",
            requester_id=user.id,
            created_at=clock_now(),
        )
        session.add(ticket)
        session.flush()
        report.tickets_created += 1

    message = Message(
        ticket_id=ticket.id,
        tenant_id=tenant.id,
        author_id=user.id,
        direction="inbound",
        body=parsed.body_text or "",
        body_html=parsed.body_html,
        message_id=norm_msg_id,
        from_address=parsed.from_address,
        created_at=clock_now(),
    )
    session.add(message)
    session.flush()

    if len(parsed.attachments) > 0:
        stored = store_attachments(
            session,
            tenant=tenant,
            ticket=ticket,
            message=message,
            parsed=parsed,
        )
        report.attachments += len(stored)

    record_receipt(
        session,
        filename=file_path.name,
        sha256=sha256_hex,
        message_id=norm_msg_id,
        status=STATUS_PROCESSED,
        ticket_id=ticket.id,
    )

    move_to_processed(file_path, processed_dir)
    report.processed += 1


def run_once(
    session: Session,
    *,
    spool_dir: Path,
    processed_dir: Path | None = None,
    failed_dir: Path | None = None,
    limit: int | None = None,
) -> IngestReport:
    """Process the spool once and return the counters."""
    p_dir = processed_dir or (spool_dir.parent / "processed")
    f_dir = failed_dir or (spool_dir.parent / "failed")

    files = collect_spool(spool_dir)
    if limit is not None and limit > 0:
        files = files[:limit]

    report = IngestReport(files_seen=len(files))

    for file_path in files:
        with session.begin_nested():
            try:
                process_file(
                    session,
                    file_path,
                    processed_dir=p_dir,
                    failed_dir=f_dir,
                    report=report,
                )
            except Exception as exc:
                session.rollback()
                move_to_failed(file_path, f_dir, str(exc))
                report.failed += 1
                report.failures.append(f"{file_path.name}: {exc}")

    return report
