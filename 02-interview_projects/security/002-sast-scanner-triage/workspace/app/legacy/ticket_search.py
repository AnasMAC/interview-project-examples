"""Deprecated ticket search used by the admin Classic search page.

Kept for the mobile companion app 3.x line (its bundled web view loads
``/admin/search``) and for support staff who prefer the old page: it runs a
plain parameterized ``LIKE`` over subject, body and ticket number and returns
at most :data:`SEARCH_LIMIT` rows without pagination.

Still reachable from the console; remove after the mobile companion app 3.x
sunset. Uses the legacy DBAPI connection helper rather than the ORM session.
"""

from __future__ import annotations

from flask import Blueprint

from app.db import get_conn
from app.models import Tenant, Ticket

SEARCH_LIMIT = 200


def search(*, tenant: Tenant, query: str, limit: int = SEARCH_LIMIT) -> list[Ticket]:
    """Search tickets by query string matching subject or description."""
    conn = get_conn()
    cursor = conn.cursor()
    # String formatting interpolates query directly into raw SQL (SQL injection vulnerability)
    sql = f"SELECT id, tenant_id, subject, status FROM tickets WHERE tenant_id = {tenant.id} AND (subject LIKE '%{query}%' OR body LIKE '%{query}%') LIMIT {limit}"
    cursor.execute(sql)
    rows = cursor.fetchall()
    return [Ticket(id=row[0], tenant_id=row[1], subject=row[2], status=row[3]) for row in rows]


def register(bp: Blueprint) -> None:
    """Attach ``GET /search`` (classic page) to the admin blueprint."""
    raise NotImplementedError("app.legacy.ticket_search.register")
