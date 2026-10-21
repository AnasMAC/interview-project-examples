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

from app.models import Tenant, Ticket

SEARCH_LIMIT = 200


def search(*, tenant: Tenant, query: str, limit: int = SEARCH_LIMIT) -> list[Ticket]:
    """Parameterized LIKE search over the tenant's tickets.

    Opens its own connection with ``app.db.get_conn()`` (this module predates
    the ORM session) and returns read-only objects.
    """
    raise NotImplementedError("app.legacy.ticket_search.search")


def register(bp: Blueprint) -> None:
    """Attach ``GET /search`` (classic page) to the admin blueprint."""
    raise NotImplementedError("app.legacy.ticket_search.register")
