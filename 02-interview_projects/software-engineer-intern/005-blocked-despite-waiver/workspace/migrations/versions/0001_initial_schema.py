"""initial schema: teams, services, keys, policies, evaluations, evidence, audit (1.0.0)

Revision ID: 0001
Revises:
Create Date: 2024-10-07 09:12:40+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("timezone", sa.String(64), server_default="Europe/London", nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_teams"),
        sa.UniqueConstraint("slug", name="uq_teams_slug"),
    )
    op.create_table(
        "services",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_services_team_id_teams"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_services"),
        sa.UniqueConstraint("team_id", "slug", name="uq_services_team_id_slug"),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_api_keys_team_id_teams"), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        _created_at(),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("prefix", name="uq_api_keys_prefix"),
        sa.CheckConstraint("role IN ('team', 'security_reviewer')", name="ck_api_keys_role"),
        sa.CheckConstraint("role = 'security_reviewer' OR team_id IS NOT NULL", name="ck_api_keys_team_scope"),
    )
    op.create_table(
        "policies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_policies_team_id_teams"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("created_by", sa.Text, nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_policies"),
        sa.UniqueConstraint("team_id", "version", name="uq_policies_team_id_version"),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_evaluations_team_id_teams"), nullable=False),
        sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id", name="fk_evaluations_service_id_services"), nullable=False),
        sa.Column("policy_id", sa.Integer, sa.ForeignKey("policies.id", name="fk_evaluations_policy_id_policies"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("pipeline_id", sa.Text, nullable=False),
        sa.Column("commit_sha", sa.String(64), nullable=False),
        sa.Column("branch", sa.Text, nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(8), nullable=False),
        sa.Column("reasons", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_evaluations"),
        sa.CheckConstraint("decision IN ('pass', 'warn', 'block')", name="ck_evaluations_decision"),
    )
    op.create_index("ix_evaluations_team_id_created_at", "evaluations", ["team_id", "created_at"])
    op.create_index("ix_evaluations_service_id_created_at", "evaluations", ["service_id", "created_at"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "evaluation_id",
            sa.BigInteger,
            sa.ForeignKey("evaluations.id", name="fk_evidence_evaluation_id_evaluations", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("data", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.UniqueConstraint("evaluation_id", "kind", name="uq_evidence_evaluation_id_kind"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_audit_events_team_id_teams"), nullable=True),
        sa.Column("actor", sa.Text, nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.BigInteger, nullable=True),
        sa.Column("details", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index("ix_audit_events_team_id_created_at", "audit_events", ["team_id", "created_at"])
    op.create_index("ix_audit_events_subject_type_subject_id", "audit_events", ["subject_type", "subject_id"])


def downgrade() -> None:
    for table in ("audit_events", "evidence", "evaluations", "policies", "api_keys", "services", "teams"):
        op.drop_table(table)
