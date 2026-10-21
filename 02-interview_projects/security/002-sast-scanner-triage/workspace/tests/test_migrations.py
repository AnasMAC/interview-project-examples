"""Migrations: the four revisions build the schema the models describe.

Coverage plan: ``alembic upgrade head`` from an empty database, ``alembic
downgrade base`` and back up, the head revision id (``0004``, so the next
revision is ``0005``), and a comparison of ``Base.metadata`` against the
migrated database (no unexpected diff).
"""

from __future__ import annotations
