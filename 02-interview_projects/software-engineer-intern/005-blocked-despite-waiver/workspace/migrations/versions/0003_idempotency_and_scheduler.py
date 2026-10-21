"""idempotency keys, waiver version ranges and expiry notices, scheduler runs (3.1.0)

Revision ID: 0003
Revises: 0002
Create Date: 2025-11-04 10:27:51+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("evaluations", sa.Column("payload_sha256", sa.String(64), nullable=True))
    # Older rows have no key; only keyed requests are unique per team.
    op.create_index(
        "uq_evaluations_team_id_idempotency_key",
        "evaluations",
        ["team_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.add_column("waivers", sa.Column("version_range", sa.String(128), nullable=True))
    op.add_column("waivers", sa.Column("expiry_notice_sent_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "scheduler_runs",
        sa.Column("job", sa.String(64), nullable=False),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("runs", sa.Integer, server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("job", name="pk_scheduler_runs"),
    )


def downgrade() -> None:
    op.drop_table("scheduler_runs")
    op.drop_column("waivers", "expiry_notice_sent_at")
    op.drop_column("waivers", "version_range")
    op.drop_index("uq_evaluations_team_id_idempotency_key", table_name="evaluations")
    op.drop_column("evaluations", "payload_sha256")
    op.drop_column("evaluations", "idempotency_key")
