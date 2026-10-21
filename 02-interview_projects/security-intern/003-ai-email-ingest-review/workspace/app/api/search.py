"""Deprecated ticket search endpoint.

``GET /api/v1/search?q=<text>&limit=<n>`` matches subject, body and ticket
number with a case-insensitive ``LIKE``. It is kept for the mobile companion
app 3.x line, is capped at :data:`SEARCH_LIMIT_MAX` results and is not
paginated; new clients use ``GET /api/v1/tickets`` filters instead.

The query is parameterized (``text()`` with a bound ``:pattern`` argument).
"""

from __future__ import annotations

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, Ticket

SEARCH_LIMIT_DEFAULT = 50
SEARCH_LIMIT_MAX = 200


def search_tickets(session: Session, *, tenant: Tenant, query: str, limit: int | None = None) -> list[Ticket]:
    """Return up to ``limit`` tickets of ``tenant`` matching ``query``."""
    raise NotImplementedError("app.api.search.search_tickets")


def register(bp: Blueprint) -> None:
    """Attach ``GET /search`` to the API blueprint."""
    raise NotImplementedError("app.api.search.register")
