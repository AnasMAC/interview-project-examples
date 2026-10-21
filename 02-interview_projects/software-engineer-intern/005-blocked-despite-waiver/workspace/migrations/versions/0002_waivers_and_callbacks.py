"""waivers, callback outbox, team callback secrets (2.0.0)

Revision ID: 0002
Revises: 0001
Create Date: 2025-03-18 14:40:05+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing teams get a generated secret; platform-security sends the new
    # value to each team out of band (runbook, "Rotating a callback secret").
    op.add_column("teams", sa.Column("callback_secret", sa.Text, nullable=True))
    op.execute(
        "UPDATE teams SET callback_secret = 'DEMO-whsec-' || slug || '-' "
        "|| substr(md5(random()::text), 1, 12)"
    )
    op.alter_column("teams", "callback_secret", nullable=False)
    op.add_column("teams", sa.Column("notify_url", sa.Text, nullable=True))
    op.add_column("evaluations", sa.Column("callback_url", sa.Text, nullable=True))

    op.create_table(
        "waivers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_waivers_team_id_teams"), nullable=False),
        sa.Column("service_id", sa.Integer, sa.ForeignKey("services.id", name="fk_waivers_service_id_services"), nullable=True),
        sa.Column("rule", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("requested_by", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("reviewed_by", sa.Text, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_waivers"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'revoked', 'expired')", name="ck_waivers_status"
        ),
    )
    op.create_index("ix_waivers_team_id_status_expires_at", "waivers", ["team_id", "status", "expires_at"])

    op.create_table(
        "callback_outbox",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("team_id", sa.Integer, sa.ForeignKey("teams.id", name="fk_callback_outbox_team_id_teams"), nullable=False),
        sa.Column(
            "evaluation_id",
            sa.BigInteger,
            sa.ForeignKey("evaluations.id", name="fk_callback_outbox_evaluation_id_evaluations"),
            nullable=True,
        ),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer, server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_callback_outbox"),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'dead')", name="ck_callback_outbox_status"),
    )
    op.create_index(
        "ix_callback_outbox_next_attempt_at_pending",
        "callback_outbox",
        ["next_attempt_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("callback_outbox")
    op.drop_table("waivers")
    op.drop_column("evaluations", "callback_url")
    op.drop_column("teams", "notify_url")
    op.drop_column("teams", "callback_secret")
