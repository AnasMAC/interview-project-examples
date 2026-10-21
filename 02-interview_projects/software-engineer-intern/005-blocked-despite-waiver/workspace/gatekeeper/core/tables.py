"""SQLAlchemy Core tables for the whole data model (ADR 0001: no ORM).

This module mirrors migrations/versions/ at head; change both together.
Timestamps are ``timestamptz`` and written from ``clock.now()`` by the code
(the server defaults only protect manual inserts). Column meanings are in
docs/architecture.md, "Data model".
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

DECISIONS = ("pass", "warn", "block")
ROLES = ("team", "security_reviewer")
WAIVER_STATUSES = ("pending", "approved", "rejected", "revoked", "expired")
OUTBOX_STATUSES = ("pending", "delivered", "dead")


def _ts(name: str, nullable: bool = False) -> sa.Column:
    if nullable:
        return sa.Column(name, sa.DateTime(timezone=True), nullable=True)
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


teams = sa.Table(
    "teams",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("slug", sa.String(64), nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/London"),
    sa.Column("callback_secret", sa.Text, nullable=False),
    sa.Column("notify_url", sa.Text, nullable=True),
    _ts("created_at"),
)

services = sa.Table(
    "services",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("slug", sa.String(64), nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    _ts("created_at"),
    sa.UniqueConstraint("team_id", "slug"),
)

api_keys = sa.Table(
    "api_keys",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("role", sa.String(32), nullable=False),
    sa.Column("prefix", sa.String(16), nullable=False, unique=True),
    sa.Column("key_hash", sa.String(64), nullable=False),
    _ts("created_at"),
    _ts("revoked_at", nullable=True),
    sa.CheckConstraint(_in("role", ROLES), name="role"),
    sa.CheckConstraint("role = 'security_reviewer' OR team_id IS NOT NULL", name="team_scope"),
)

policies = sa.Table(
    "policies",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("comment", sa.Text, nullable=True),
    sa.Column("created_by", sa.Text, nullable=False),
    _ts("created_at"),
    sa.UniqueConstraint("team_id", "version"),
)

evaluations = sa.Table(
    "evaluations",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id"), nullable=False),
    sa.Column("policy_id", sa.Integer, sa.ForeignKey("policies.id"), nullable=True),
    sa.Column("source", sa.String(32), nullable=False),
    sa.Column("pipeline_id", sa.Text, nullable=False),
    sa.Column("commit_sha", sa.String(64), nullable=False),
    sa.Column("branch", sa.Text, nullable=False),
    sa.Column("environment", sa.String(32), nullable=False),
    sa.Column("version", sa.String(64), nullable=True),
    sa.Column("decision", sa.String(8), nullable=False),
    sa.Column("reasons", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("callback_url", sa.Text, nullable=True),
    sa.Column("idempotency_key", sa.String(128), nullable=True),
    sa.Column("payload_sha256", sa.String(64), nullable=True),
    _ts("created_at"),
    sa.CheckConstraint(_in("decision", DECISIONS), name="decision"),
    sa.Index("ix_evaluations_team_id_created_at", "team_id", "created_at"),
    sa.Index("ix_evaluations_service_id_created_at", "service_id", "created_at"),
    sa.Index(
        "uq_evaluations_team_id_idempotency_key",
        "team_id",
        "idempotency_key",
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    ),
)

evidence = sa.Table(
    "evidence",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column(
        "evaluation_id",
        sa.BigInteger,
        sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("kind", sa.String(32), nullable=False),
    sa.Column("data", JSONB, nullable=False),
    sa.UniqueConstraint("evaluation_id", "kind"),
)

waivers = sa.Table(
    "waivers",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id"), nullable=True),
    sa.Column("rule", sa.String(64), nullable=False),
    sa.Column("version_range", sa.String(128), nullable=True),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("requested_by", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    sa.Column("reviewed_by", sa.Text, nullable=True),
    _ts("reviewed_at", nullable=True),
    sa.Column("review_note", sa.Text, nullable=True),
    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    _ts("expiry_notice_sent_at", nullable=True),
    _ts("created_at"),
    sa.CheckConstraint(_in("status", WAIVER_STATUSES), name="status"),
    sa.Index("ix_waivers_team_id_status_expires_at", "team_id", "status", "expires_at"),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=True),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("action", sa.String(64), nullable=False),
    sa.Column("subject_type", sa.String(32), nullable=False),
    sa.Column("subject_id", sa.BigInteger, nullable=True),
    sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    _ts("created_at"),
    sa.Index("ix_audit_events_team_id_created_at", "team_id", "created_at"),
    sa.Index("ix_audit_events_subject_type_subject_id", "subject_type", "subject_id"),
)

callback_outbox = sa.Table(
    "callback_outbox",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id"), nullable=False),
    sa.Column("evaluation_id", sa.BigInteger, sa.ForeignKey("evaluations.id"), nullable=True),
    sa.Column("event", sa.String(64), nullable=False),
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    _ts("next_attempt_at"),
    sa.Column("last_error", sa.Text, nullable=True),
    _ts("created_at"),
    _ts("delivered_at", nullable=True),
    sa.CheckConstraint(_in("status", OUTBOX_STATUSES), name="status"),
    sa.Index(
        "ix_callback_outbox_next_attempt_at_pending",
        "next_attempt_at",
        postgresql_where=sa.text("status = 'pending'"),
    ),
)

scheduler_runs = sa.Table(
    "scheduler_runs",
    metadata,
    sa.Column("job", sa.String(64), primary_key=True),
    _ts("last_started_at", nullable=True),
    _ts("last_finished_at", nullable=True),
    sa.Column("last_status", sa.String(16), nullable=True),
    sa.Column("last_error", sa.Text, nullable=True),
    sa.Column("runs", sa.Integer, nullable=False, server_default="0"),
)
