"""Factories and small utilities shared by the test modules.

Everything here is deterministic: no wall clock (``TODAY`` is the world's
"today"), no random emails, no fixed ports. Factories ``flush`` so the caller
can use ids, but they do not commit - commit before making a request that has
to see the rows (the ``tenant``/``user``/``ticket`` fixtures in conftest commit
for you).
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.passwords import demo_password, hash_password
from app.auth.tokens import issue_token
from app.config import Settings, get_settings
from app.db import Base
from app.models import (
    Attachment,
    AuditEvent,
    IngestReceipt,
    Message,
    Tenant,
    Ticket,
    User,
    Webhook,
    WebhookDelivery,
)

TODAY = datetime(2026, 5, 11, 9, 0, tzinfo=ZoneInfo("Europe/London"))
ROOT = Path(__file__).resolve().parents[1]

_CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


# --- settings and clock -------------------------------------------------------


def current_settings() -> Settings:
    """The settings the tests run with."""
    return get_settings()


# --- factories ----------------------------------------------------------------


def build_tenant(
    session: Session,
    *,
    slug: str = "brightpath",
    name: str | None = None,
    prefix: str | None = None,
    plan: str = "growth",
    timezone: str = "Europe/London",
    status: str = "active",
    created_at: datetime | None = None,
) -> Tenant:
    """Create a tenant (Brightpath Labs by default)."""
    tenant = Tenant(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        prefix=prefix or slug[:3].upper(),
        plan=plan,
        timezone=timezone,
        status=status,
        created_at=created_at or TODAY,
    )
    session.add(tenant)
    session.flush()
    return tenant


@lru_cache(maxsize=64)
def _cached_hash(password: str) -> str:
    """Hash each demo password once: pbkdf2 is deliberately slow."""
    return hash_password(password)


def build_user(
    session: Session,
    tenant: Tenant,
    *,
    email: str | None = None,
    name: str | None = None,
    role: str = "agent",
    password: str | None = None,
    status: str = "active",
    created_at: datetime | None = None,
    last_login_at: datetime | None = None,
) -> User:
    """Create a user in ``tenant``; the password defaults to ``DEMO-<slug>-<role>``."""
    address = email or f"{role}@{tenant.slug}.test"
    user = User(
        tenant_id=tenant.id,
        email=address,
        name=name or address.split("@")[0].replace(".", " ").title(),
        role=role,
        password_hash=_cached_hash(password or demo_password(tenant.slug, role)),
        status=status,
        created_at=created_at or TODAY,
        last_login_at=last_login_at,
    )
    session.add(user)
    session.flush()
    return user


def next_ticket_number(session: Session, tenant: Tenant, *, start: int = 1000) -> str:
    """Next free ``<prefix>-<sequence>`` for the tenant."""
    highest = start
    numbers = session.scalars(select(Ticket.number).where(Ticket.tenant_id == tenant.id)).all()
    for number in numbers:
        _, _, sequence = number.partition("-")
        if sequence.isdigit():
            highest = max(highest, int(sequence))
    return f"{tenant.prefix}-{highest + 1}"


def build_ticket(
    session: Session,
    tenant: Tenant,
    *,
    requester: User | None = None,
    assignee: User | None = None,
    subject: str = "Refund for order 1042",
    body: str = "The parcel arrived two days late and one item was damaged.",
    status: str = "new",
    priority: str = "normal",
    channel: str = "web",
    number: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    solved_at: datetime | None = None,
) -> Ticket:
    """Create a ticket for ``tenant``."""
    created = created_at or TODAY
    ticket = Ticket(
        tenant_id=tenant.id,
        number=number or next_ticket_number(session, tenant),
        subject=subject,
        body=body,
        status=status,
        priority=priority,
        channel=channel,
        requester_id=requester.id if requester else None,
        assignee_id=assignee.id if assignee else None,
        created_at=created,
        updated_at=updated_at or created,
        solved_at=solved_at,
    )
    session.add(ticket)
    session.flush()
    return ticket


def build_message(
    session: Session,
    ticket: Ticket,
    *,
    author: User | None = None,
    direction: str = "inbound",
    body: str = "Any update on this?",
    body_html: str | None = None,
    message_id: str | None = None,
    from_address: str | None = None,
    created_at: datetime | None = None,
) -> Message:
    """Create a message on ``ticket``."""
    message = Message(
        ticket_id=ticket.id,
        tenant_id=ticket.tenant_id,
        author_id=author.id if author else None,
        direction=direction,
        body=body,
        body_html=body_html,
        message_id=message_id,
        from_address=from_address or (author.email if author else None),
        created_at=created_at or TODAY,
    )
    session.add(message)
    session.flush()
    return message


def build_attachment(
    session: Session,
    tenant: Tenant,
    ticket: Ticket,
    *,
    filename: str = "sla-notice.txt",
    content_type: str = "text/plain",
    data: bytes = b"Bellpost demo attachment\n",
    uploader: User | None = None,
    message: Message | None = None,
    created_at: datetime | None = None,
) -> Attachment:
    """Write a real file below the attachment root and create its row."""
    from app.attachments.storage import storage_path, to_stored_path

    digest = hashlib.sha256(data).hexdigest()
    path = storage_path(tenant.id, ticket.id, digest, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    attachment = Attachment(
        tenant_id=tenant.id,
        ticket_id=ticket.id,
        message_id=message.id if message else None,
        uploader_id=uploader.id if uploader else None,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=digest,
        storage_path=to_stored_path(path),
        created_at=created_at or TODAY,
    )
    session.add(attachment)
    session.flush()
    return attachment


def build_webhook(
    session: Session,
    tenant: Tenant,
    *,
    url: str = "http://127.0.0.1:8900/hooks/brightpath",
    events: Iterable[str] = ("ticket.created", "message.created"),
    enabled: bool = True,
    secret: str = "DEMO-whsec-brp-0001",
    created_at: datetime | None = None,
) -> Webhook:
    """Create a webhook subscribed to ``events``."""
    webhook = Webhook(
        tenant_id=tenant.id,
        url=url,
        secret=secret,
        events=list(events),
        enabled=enabled,
        created_at=created_at or TODAY,
    )
    session.add(webhook)
    session.flush()
    return webhook


def build_delivery(
    session: Session,
    webhook: Webhook,
    *,
    event: str = "ticket.created",
    payload: dict[str, Any] | None = None,
    status: str = "pending",
    attempts: int = 0,
    next_attempt_at: datetime | None = None,
    last_status_code: int | None = None,
    created_at: datetime | None = None,
) -> WebhookDelivery:
    """Create a delivery row for ``webhook``."""
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        tenant_id=webhook.tenant_id,
        event=event,
        payload=payload or {"event": event, "tenant": webhook.tenant_id, "data": {}},
        status=status,
        attempts=attempts,
        next_attempt_at=next_attempt_at,
        last_status_code=last_status_code,
        created_at=created_at or TODAY,
        updated_at=created_at or TODAY,
    )
    session.add(delivery)
    session.flush()
    return delivery


def build_audit_event(
    session: Session,
    tenant: Tenant,
    *,
    actor: User | None = None,
    action: str = "ticket.created",
    target_type: str | None = "ticket",
    target_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> AuditEvent:
    """Create an audit event row."""
    event = AuditEvent(
        tenant_id=tenant.id,
        actor_id=actor.id if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail or {},
        created_at=created_at or TODAY,
    )
    session.add(event)
    session.flush()
    return event


def build_receipt(
    session: Session,
    *,
    filename: str = "incoming-0001.eml",
    sha256: str | None = None,
    message_id: str | None = None,
    status: str = "processed",
    ticket: Ticket | None = None,
    error: str | None = None,
    processed_at: datetime | None = None,
) -> IngestReceipt:
    """Create an ``ingest_receipts`` row."""
    receipt = IngestReceipt(
        filename=filename,
        sha256=sha256 or hashlib.sha256(filename.encode()).hexdigest(),
        message_id=message_id,
        status=status,
        ticket_id=ticket.id if ticket else None,
        error=error,
        processed_at=processed_at or TODAY,
    )
    session.add(receipt)
    session.flush()
    return receipt


def issue_user_token(session: Session, tenant: Tenant, user: User, *, name: str = "pytest") -> str:
    """Issue a bearer token and return the plaintext (caller commits)."""
    return issue_token(session, tenant=tenant, user=user, name=name).plaintext


# --- HTTP helpers -------------------------------------------------------------


def auth_header(token: str) -> dict[str, str]:
    """``{"Authorization": "Bearer <token>"}``."""
    return {"Authorization": f"Bearer {token}"}


def login(client: Any, email: str, password: str, *, url: str = "/admin/login") -> Any:
    """Sign in through the console form, fetching the CSRF token first."""
    page = client.get(url)
    data = {"email": email, "password": password}
    match = _CSRF_RE.search(page.get_data(as_text=True))
    if match:
        data["csrf_token"] = match.group(1)
    return client.post(url, data=data, follow_redirects=False)


def logout(client: Any, *, url: str = "/admin/logout") -> Any:
    """Sign out through the console form."""
    page = client.get("/admin/")
    data: dict[str, str] = {}
    match = _CSRF_RE.search(page.get_data(as_text=True))
    if match:
        data["csrf_token"] = match.group(1)
    return client.post(url, data=data, follow_redirects=False)


def assert_error(response: Any, status: int, code: str) -> dict:
    """Assert a JSON error body has the expected status and code."""
    assert response.status_code == status, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload is not None, "expected a JSON error body"
    assert payload["error"]["code"] == code, payload
    return payload


# --- email fixtures -----------------------------------------------------------


def make_eml(
    *,
    from_addr: str = "sana.iqbal@brightpath.test",
    to_addr: str = "support@brightpath.test",
    subject: str = "Where is my parcel?",
    body: str = "Hello, the tracking page has not moved since Tuesday.",
    message_id: str | None = None,
    in_reply_to: str | None = None,
    references: Iterable[str] | None = None,
    sent_at: datetime | None = None,
    attachments: Iterable[tuple[str, str, bytes]] = (),
) -> bytes:
    """Build an ``.eml`` file: text body plus optional ``(filename, type, bytes)`` parts."""
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = to_addr
    message["Subject"] = subject
    message["Date"] = format_datetime(sent_at or TODAY)
    message["Message-ID"] = message_id or f"<{uuid4().hex}@brightpath.test>"
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = " ".join(references)
    message.set_content(body)
    for filename, content_type, payload in attachments:
        maintype, _, subtype = content_type.partition("/")
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    return message.as_bytes()


def write_eml(directory: Path, name: str, raw: bytes) -> Path:
    """Write an ``.eml`` file into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(raw)
    return path


# --- database helpers ---------------------------------------------------------


def truncate_all(engine: Any) -> None:
    """Empty every table and reset sequences (between tests)."""
    # Table names come from our own metadata, never from input.
    preparer = engine.dialect.identifier_preparer
    names = ", ".join(preparer.quote(table.name) for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE TABLE " + names + " RESTART IDENTITY CASCADE"))


# --- local mocks --------------------------------------------------------------


def wait_for_port(port: int, *, host: str = "127.0.0.1", timeout: float = 10.0) -> bool:
    """Wait until something answers on ``host:port``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            probe.settimeout(0.25)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.1)
    return False


def free_port() -> int:
    """An unused port on 127.0.0.1."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class MockServer:
    """A ``tools/`` mock running as a subprocess."""

    name: str
    port: int
    process: subprocess.Popen
    url: str
    log_path: Path | None = None
    output_path: Path | None = None

    def deliveries(self) -> list[dict[str, Any]]:
        """Every record the mock appended to its JSONL log."""
        if self.log_path is None or not self.log_path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    def output(self) -> str:
        """Captured stdout/stderr of the process."""
        if self.output_path is None or not self.output_path.exists():
            return ""
        return self.output_path.read_text(encoding="utf-8", errors="replace")

    def stop(self) -> None:
        """Terminate the process (idempotent)."""
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                self.process.kill()
                self.process.wait(timeout=5)


def _start_mock(
    name: str,
    script: Path,
    port: int,
    *,
    extra_args: Iterable[str] = (),
    log_path: Path | None = None,
    output_dir: Path | None = None,
) -> MockServer:
    output_path = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{name}.out"
    output_handle: Any = output_path.open("w", encoding="utf-8") if output_path else subprocess.DEVNULL
    process = subprocess.Popen(
        [sys.executable, str(script), "--port", str(port), *extra_args],
        cwd=str(ROOT),
        stdout=output_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        if not wait_for_port(port) or process.poll() is not None:
            process.terminate()
            raise RuntimeError(
                f"{name} did not answer on 127.0.0.1:{port} "
                "(is something else already listening on that port?)"
            )
    finally:
        if hasattr(output_handle, "close"):
            output_handle.close()
    return MockServer(
        name=name,
        port=port,
        process=process,
        url=f"http://127.0.0.1:{port}",
        log_path=log_path,
        output_path=output_path,
    )


def start_mockhook(
    *,
    port: int,
    log_path: Path,
    strict: bool = False,
    secret: str = "DEMO-whsec-test-mockhook",
    output_dir: Path | None = None,
) -> MockServer:
    """Start ``tools/mockhook/server.py`` on ``port``."""
    args = ["--log", str(log_path), "--secret", secret]
    if strict:
        args.append("--strict")
    return _start_mock(
        "mockhook",
        ROOT / "tools" / "mockhook" / "server.py",
        port,
        extra_args=args,
        log_path=log_path,
        output_dir=output_dir,
    )


def start_mock_metadata(*, port: int, output_dir: Path | None = None) -> MockServer:
    """Start ``tools/mock_metadata/server.py`` on ``port``."""
    return _start_mock(
        "mock_metadata",
        ROOT / "tools" / "mock_metadata" / "server.py",
        port,
        output_dir=output_dir,
    )


def tomorrow() -> datetime:
    """``TODAY`` plus one day (for retry assertions)."""
    return TODAY + timedelta(days=1)
