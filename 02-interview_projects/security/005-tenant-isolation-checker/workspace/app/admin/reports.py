"""Reports (``/admin/reports``): per-status and per-day counts for one tenant.

Day buckets are computed in the **tenant's** timezone (the admin list pages
use the tenant timezone too; only the Activity page renders UTC). The range is
inclusive on both ends and the counts come from grouped queries, never from a
loop over days issuing one query each.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint
from sqlalchemy.orm import Session

from app.models import Tenant


def status_counts(session: Session, *, tenant: Tenant) -> dict[str, int]:
    """Ticket count per status, including the statuses with zero tickets."""
    raise NotImplementedError("app.admin.reports.status_counts")


def daily_counts(
    session: Session, *, tenant: Tenant, since: date, until: date
) -> list[dict[str, object]]:
    """New-ticket counts per day between ``since`` and ``until`` (inclusive)."""
    raise NotImplementedError("app.admin.reports.daily_counts")


def register(bp: Blueprint) -> None:
    """Attach the report routes to the admin blueprint."""
    raise NotImplementedError("app.admin.reports.register")
