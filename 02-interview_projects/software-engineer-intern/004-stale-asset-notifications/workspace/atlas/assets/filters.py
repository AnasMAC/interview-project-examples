"""Asset search filters shared by the API and the dashboard.

Both take the same query parameters, so a dashboard URL, a saved view and an
API call with the same querystring list the same assets:

* ``kind`` (repeatable, any of), ``tag`` (repeatable, all of),
* ``owner=<team>`` or ``owner=-`` for unowned assets (repeatable, any of),
* ``exposure=<rule>`` or ``exposure=any``: assets with an open exposure,
* ``changed_since=<ISO 8601 with offset>`` and ``changed_within=<hours>``:
  assets with at least one history row in the window,
* ``q``: case-insensitive substring of the key or the label,
* ``include_archived=1``: archived assets are hidden otherwise.

Every condition on a related table is an ``EXISTS`` subquery, so the result
never holds the same asset twice and can be annotated or counted safely.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from urllib.parse import urlencode

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.http import QueryDict

from atlas.assets.models import Asset, AssetChange
from atlas.core.models import Org
from atlas.exposure.models import Exposure

FILTER_PARAMS = (
    "kind", "tag", "owner", "exposure", "changed_since", "changed_within", "q", "include_archived",
)
UNOWNED = "-"
ANY_EXPOSURE = "any"
MAX_WITHIN_HOURS = 24 * 90
Params = Mapping[str, list[str]] | QueryDict
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


class InvalidFilter(ValueError):
    def __init__(self, param: str, message: str):
        super().__init__(message)
        self.param = param


def _values(params: Params, name: str) -> list[str]:
    if hasattr(params, "getlist"):
        raw = params.getlist(name)
    else:
        raw = params.get(name, [])
        raw = [raw] if isinstance(raw, str) else list(raw)
    return [value.strip() for value in raw if value is not None and value.strip() != ""]


def _last(params: Params, name: str) -> str | None:
    values = _values(params, name)
    return values[-1] if values else None


def parse_aware_datetime(param: str, text: str) -> datetime:
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        raise InvalidFilter(param, f"Not an ISO 8601 date-time: {text!r}.") from None
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidFilter(param, "Give a UTC offset, e.g. 2026-11-04T09:30:00-05:00 or ...Z.")
    return value


def _within_hours(text: str) -> int:
    try:
        hours = int(text)
    except ValueError:
        raise InvalidFilter("changed_within", f"Expected a whole number of hours, got {text!r}.") from None
    if not 1 <= hours <= MAX_WITHIN_HOURS:
        raise InvalidFilter("changed_within", f"Must be between 1 and {MAX_WITHIN_HOURS} hours.")
    return hours


def _changed_since(org: Org, since: datetime):
    return Exists(AssetChange.objects.for_org(org).filter(asset=OuterRef("pk"), occurred_at__gte=since))


def filter_assets(queryset: QuerySet[Asset], params: Params, *, org: Org) -> QuerySet[Asset]:
    """Apply the asset-list filters in ``params``; raises ``InvalidFilter``."""
    queryset = queryset.filter(org=org)

    kinds = _values(params, "kind")
    unknown = sorted(set(kinds) - set(Asset.Kind.values))
    if unknown:
        raise InvalidFilter("kind", f"Unknown kind(s): {', '.join(unknown)}.")
    if kinds:
        queryset = queryset.filter(kind__in=kinds)

    for name in sorted(set(_values(params, "tag"))):
        through = Asset.tags.through.objects.filter(asset_id=OuterRef("pk"), tag__org=org, tag__name=name)
        queryset = queryset.filter(Exists(through))

    owners = _values(params, "owner")
    if owners:
        queryset = queryset.filter(owner_team__in=["" if o == UNOWNED else o for o in owners])

    exposures = set(_values(params, "exposure"))
    if exposures:
        open_exposures = Exposure.objects.for_org(org).filter(
            asset=OuterRef("pk"), status=Exposure.Status.OPEN
        )
        if ANY_EXPOSURE not in exposures:
            unknown = sorted(exposures - set(Exposure.Rule.values))
            if unknown:
                raise InvalidFilter("exposure", f"Unknown rule(s): {', '.join(unknown)}; or use 'any'.")
            open_exposures = open_exposures.filter(rule__in=exposures)
        queryset = queryset.filter(Exists(open_exposures))

    since_text = _last(params, "changed_since")
    if since_text is not None:
        queryset = queryset.filter(_changed_since(org, parse_aware_datetime("changed_since", since_text)))

    within_text = _last(params, "changed_within")
    if within_text is not None:
        hours = _within_hours(within_text)
        # Imported here: notify depends on assets, not the other way round.
        from atlas.notify.changes import window_start

        queryset = queryset.filter(_changed_since(org, window_start(org, hours)))

    q = _last(params, "q")
    if q is not None:
        queryset = queryset.filter(Q(key__icontains=q) | Q(label__icontains=q))

    archived = (_last(params, "include_archived") or "0").lower()
    if archived not in _TRUE | _FALSE:
        raise InvalidFilter("include_archived", "Use 1 or 0.")
    if archived in _FALSE:
        queryset = queryset.filter(archived_at__isnull=True)
    return queryset


def canonical_querystring(params: Params) -> str:
    """Known filters only, empty values dropped, keys and values sorted, URL-encoded."""
    pairs = []
    for name in sorted(FILTER_PARAMS):
        pairs.extend((name, value) for value in sorted(set(_values(params, name))))
    return urlencode(pairs)
