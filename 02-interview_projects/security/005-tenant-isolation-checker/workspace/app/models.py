"""SQLAlchemy models and the vocabulary the rest of the product shares.

The schema is the sum of the four Alembic revisions in ``migrations/versions``
(``0001_initial``, ``0002_attachments``, ``0003_webhooks_and_receipts``,
``0004_audit_detail``); the next revision number is ``0005``.

Vocabulary (roles, statuses, transitions, webhook events, audit actions) lives
here so the API, the admin panel, the ingest worker and the seed cannot drift
apart. Timestamps are ``timestamptz`` and come from :func:`app.clock.now`, so a
frozen clock produces reproducible demo data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import now as clock_now
from app.db import Base

# --- vocabulary ---------------------------------------------------------------

ROLE_REQUESTER = "requester"
ROLE_AGENT = "agent"
ROLE_ADMIN = "admin"
ROLES = (ROLE_REQUESTER, ROLE_AGENT, ROLE_ADMIN)

TENANT_PLANS = ("starter", "growth", "scale")
TENANT_STATUSES = ("active", "suspended")

USER_STATUSES = ("active", "disabled", "invited")

TICKET_NEW = "new"
TICKET_STATUSES = ("new", "open", "pending", "solved", "closed")
TICKET_PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_CHANNELS = ("web", "email")

#: The only status changes the ticket state machine accepts; anything else is
#: answered with 409 ``invalid_transition``.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"open"}),
    "open": frozenset({"pending", "solved"}),
    "pending": frozenset({"open", "solved"}),
    "solved": frozenset({"closed", "open"}),
    "closed": frozenset({"open"}),
}

MESSAGE_DIRECTIONS = ("inbound", "outbound")

WEBHOOK_EVENTS = (
    "ticket.created",
    "ticket.updated",
    "ticket.solved",
    "message.created",
    "attachment.created",
)

WEBHOOK_DELIVERY_STATUSES = ("pending", "delivered", "failed", "dead")

INGEST_RECEIPT_STATUSES = ("processed", "duplicate", "unsupported", "failed")

AUDIT_ACTIONS = (
    "admin.login",
    "admin.logout",
    "ticket.created",
    "ticket.status_changed",
    "ticket.assigned",
    "message.created",
    "attachment.uploaded",
    "attachment.downloaded",
    "user.created",
    "user.role_changed",
    "token.created",
    "token.revoked",
    "webhook.updated",
    "ingest.failed",
    "ingest.duplicate",
)


def can_transition(current: str, target: str) -> bool:
    """True when ``current -> target`` is an allowed ticket status change."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


# --- tables -------------------------------------------------------------------


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenants_slug"),
        UniqueConstraint("prefix", name="uq_tenants_prefix"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Three upper-case letters; ticket numbers are ``<prefix>-<sequence>``.
    prefix: Mapped[str] = mapped_column(String(3), nullable=False)
    plan: Mapped[str] = mapped_column(String(20), nullable=False, default="starter")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    users: Mapped[list[User]] = relationship(back_populates="tenant")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="tenant")
    webhooks: Mapped[list[Webhook]] = relationship(back_populates="tenant")

    def __repr__(self) -> str:
        return f"<Tenant {self.slug}>"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        Index("ix_users_tenant_role", "tenant_id", "role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_REQUESTER)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    api_tokens: Mapped[list[ApiToken]] = relationship(back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_api_tokens_prefix"),
        Index("ix_api_tokens_tenant_id", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: First 12 characters of the plaintext token; the lookup key.
    prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship()
    user: Mapped[User] = relationship(back_populates="api_tokens")


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_tickets_tenant_number"),
        Index("ix_tickets_tenant_created", "tenant_id", "created_at"),
        Index("ix_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_tickets_requester_id", "requester_id"),
        Index("ix_tickets_assignee_id", "assignee_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    #: ``<tenant prefix>-<sequence>``, sequence starts at 1001 per tenant.
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TICKET_NEW)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="web")
    #: NULL for tickets that arrived from an unknown sender (email ingest).
    requester_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now, onupdate=clock_now
    )
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship(back_populates="tickets")
    messages: Mapped[list[Message]] = relationship(back_populates="ticket")
    attachments: Mapped[list[Attachment]] = relationship(back_populates="ticket")
    requester: Mapped[User | None] = relationship(foreign_keys=[requester_id])
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])

    def __repr__(self) -> str:
        return f"<Ticket {self.number} {self.status}>"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_ticket_created", "ticket_id", "created_at"),
        Index("ix_messages_tenant_message_id", "tenant_id", "message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL for email that nobody in the tenant sent.
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="inbound")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_html: Mapped[str | None] = mapped_column(Text)
    #: RFC 5322 Message-ID as received (no angle brackets).
    message_id: Mapped[str | None] = mapped_column(String(255))
    from_address: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    ticket: Mapped[Ticket] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship(foreign_keys=[author_id])
    attachments: Mapped[list[Attachment]] = relationship(back_populates="message")


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_ticket_id", "ticket_id"),
        Index("ix_attachments_message_id", "message_id"),
        Index("ix_attachments_tenant_sha256", "tenant_id", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    uploader_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Path below BELLPOST_ATTACHMENT_ROOT as
    #: ``<tenant_id>/<ticket_id>/<sha256[:2]>/<uuid4>.<ext>``.
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    message: Mapped[Message | None] = relationship(back_populates="attachments")
    uploader: Mapped[User | None] = relationship(foreign_keys=[uploader_id])


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_events_tenant_action", "tenant_id", "action"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    #: NULL for actions the system took on its own (ingest, delivery retries).
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    #: Stringified row id (or slug) of the target resource.
    target_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id])


class Webhook(Base):
    __tablename__ = "webhooks"
    __table_args__ = (Index("ix_webhooks_tenant_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    #: Signing secret; starts with ``DEMO-whsec-`` in demo data.
    secret: Mapped[str] = mapped_column(String(120), nullable=False)
    events: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    tenant: Mapped[Tenant] = relationship(back_populates="webhooks")
    deliveries: Mapped[list[WebhookDelivery]] = relationship(back_populates="webhook")


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_status_next", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_webhook_created", "webhook_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_id: Mapped[int] = mapped_column(
        ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now, onupdate=clock_now
    )

    webhook: Mapped[Webhook] = relationship(back_populates="deliveries")


class IngestReceipt(Base):
    __tablename__ = "ingest_receipts"
    __table_args__ = (
        Index("ix_ingest_receipts_message_id", "message_id"),
        Index("ix_ingest_receipts_sha256", "sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: RFC 5322 Message-ID (no angle brackets) when the file carried one.
    message_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    ticket_id: Mapped[int | None] = mapped_column(
        ForeignKey("tickets.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=clock_now
    )

    ticket: Mapped[Ticket | None] = relationship(foreign_keys=[ticket_id])
