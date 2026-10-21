"""The hand-written migrations must produce exactly the schema the models describe."""

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.core.config import REPO_ROOT
from app.models import Base


def test_migrated_schema_matches_models(engine):
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_single_head_and_database_is_at_head(engine):
    script = ScriptDirectory.from_config(Config(str(REPO_ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == heads[0]


def test_expected_tables_exist(engine):
    tables = set(inspect(engine).get_table_names())
    assert {
        "tenants",
        "api_tokens",
        "assets",
        "scan_profiles",
        "scans",
        "jobs",
        "findings",
        "finding_events",
        "webhooks",
        "outbox",
        "reports",
    } <= tables
