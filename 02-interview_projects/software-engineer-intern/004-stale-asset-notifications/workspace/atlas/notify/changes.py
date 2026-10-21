"""Change detection. "Last 24 h" is 24 elapsed hours, not "since this time yesterday".

They differ on DST days: on 2026-11-01 Toronto fell back, and wall-clock
arithmetic gave a 25 h window that day (23 h when clocks spring forward).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.db.models import QuerySet

from atlas.assets.models import AssetChange
from atlas.core import clock
from atlas.core.models import Org


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def window_start(org: Org, hours: int = 24, *, now: datetime | None = None) -> datetime:
    """Start of the org's "last ``hours`` hours"; the org's timezone deliberately plays no part."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    now = clock.now() if now is None else now
    _require_aware(now, "now")
    # Python subtracts wall-clock time when both sides share a ZoneInfo, so
    # convert first: UTC has no DST.
    return now.astimezone(UTC) - timedelta(hours=hours)


def changed_asset_ids(org: Org, since: datetime) -> QuerySet:
    """Ids of the org's assets with a change at or after ``since`` (usable in ``id__in``)."""
    _require_aware(since, "since")
    return (
        AssetChange.objects.for_org(org)
        .filter(occurred_at__gte=since)
        .order_by()
        .values_list("asset_id", flat=True)
        .distinct()
    )
