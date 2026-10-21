"""index cleanup on findings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-06 14:20:00+00:00

Drops ix_findings_tenant_id_last_seen_at. Every findings query filters on
tenant_id first, and ix_findings_tenant_id_status already leads with it, so
the second (tenant_id, ...) index is redundant for lookups. It is not free:
ingest moves last_seen_at on every finding a scan sees again, and an indexed
column change rules out HOT updates, so each observe rewrote an index entry
as well as the row. On the large tenants' nightly runs that was most of the
write volume on findings.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_findings_tenant_id_last_seen_at"), table_name="findings")


def downgrade() -> None:
    op.create_index(
        op.f("ix_findings_tenant_id_last_seen_at"), "findings", ["tenant_id", "last_seen_at"]
    )
