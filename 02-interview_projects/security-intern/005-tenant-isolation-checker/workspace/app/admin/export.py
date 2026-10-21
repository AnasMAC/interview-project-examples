"""CSV export of the filtered ticket list (``/admin/tickets.csv``).

Rows are streamed so a tenant with thousands of tickets does not need the
whole result set in memory, and every cell goes through :func:`_cell`, which
prefixes ``=``, ``+``, ``-``, ``@``, tab and carriage return with an apostrophe
so spreadsheet software cannot evaluate exported values as formulas.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant, Ticket

COLUMNS = (
    "number",
    "subject",
    "status",
    "priority",
    "channel",
    "requester",
    "assignee",
    "created_at",
    "updated_at",
    "solved_at",
)


def _cell(value: Any) -> str:
    """Render one CSV cell, neutralising spreadsheet formulas."""
    raise NotImplementedError("app.admin.export._cell")


def ticket_rows(tickets: Iterator[Ticket]) -> Iterator[list[str]]:
    """Yield one CSV row per ticket."""
    raise NotImplementedError("app.admin.export.ticket_rows")


def write_csv(tickets: Iterator[Ticket]) -> Iterator[str]:
    """Yield the CSV document in chunks."""
    raise NotImplementedError("app.admin.export.write_csv")


def export_for(session: Session, *, tenant: Tenant, status: str | None = None) -> Iterator[str]:
    """Stream the export for the current tenant and filter."""
    raise NotImplementedError("app.admin.export.export_for")


def register(bp: Blueprint) -> None:
    """Attach the export route to the admin blueprint."""
    raise NotImplementedError("app.admin.export.register")
