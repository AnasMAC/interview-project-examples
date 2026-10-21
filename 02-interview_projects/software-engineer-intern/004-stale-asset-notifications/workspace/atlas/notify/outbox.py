"""Transactional outbox: one row per (event, enabled subscribed webhook of the org).

Written in the caller's transaction, so a rolled-back import sends nothing
and a committed one always has its events; ``delivery.deliver_due`` sends them.
"""

from __future__ import annotations

from collections.abc import Sequence

from atlas.assets.models import Asset, AssetChange
from atlas.core import clock
from atlas.core.models import Org
from atlas.exposure.models import Exposure
from atlas.notify.models import EVENTS, OutboxEvent, Webhook

_EXPOSURE_EVENTS = {
    AssetChange.Kind.EXPOSURE_OPENED: "exposure.opened",
    AssetChange.Kind.EXPOSURE_RESOLVED: "exposure.resolved",
}


def _rows(org: Org, hooks: list[Webhook], event: str, data: dict) -> list[OutboxEvent]:
    if event not in EVENTS:
        raise ValueError(f"unknown webhook event {event!r}")
    return [OutboxEvent(org=org, webhook=h, event=event, payload=data) for h in hooks if event in h.events]


def _enabled_hooks(org: Org) -> list[Webhook]:
    return list(Webhook.objects.for_org(org).filter(enabled=True).order_by("id"))


def enqueue(org: Org, event: str, data: dict) -> list[OutboxEvent]:
    return OutboxEvent.objects.bulk_create(_rows(org, _enabled_hooks(org), event, data))


def _asset_data(asset: Asset) -> dict:
    return {"id": asset.id, "kind": asset.kind, "key": asset.key, "label": asset.label,
            "owner_team": asset.owner_team}


def _change_data(change: AssetChange) -> dict:
    return {"kind": change.kind, "field": change.field, "old": change.old_value, "new": change.new_value}


def _exposure_data(exposure: Exposure) -> dict:
    return {
        "id": exposure.id, "rule": exposure.rule, "subject": exposure.subject, "severity": exposure.severity,
        "title": exposure.title, "opened_at": clock.isoformat(exposure.opened_at),
        "resolved_at": clock.isoformat(exposure.resolved_at) if exposure.resolved_at else None,
    }


def group_changes(org: Org, changes: Sequence[AssetChange]) -> list[tuple[str, dict]]:
    """``(event, data)`` pairs for a batch of changes, per asset in first-seen order.

    An asset with a ``created`` change gives one ``asset.created`` carrying all
    its non-exposure changes; otherwise those give one ``asset.changed``. Each
    exposure change gives its own ``exposure.opened`` / ``exposure.resolved``.
    """
    if any(change.org_id != org.id for change in changes):
        raise ValueError("publish_changes() got a change of another org")
    by_asset: dict[int, list[AssetChange]] = {}
    for change in changes:
        by_asset.setdefault(change.asset_id, []).append(change)
    assets = Asset.objects.for_org(org).in_bulk(list(by_asset))
    exposure_ids = [c.new_value["exposure_id"] for c in changes if c.kind in _EXPOSURE_EVENTS]
    found = Exposure.objects.for_org(org).in_bulk(exposure_ids)
    exposures = {pk: _exposure_data(exposure) for pk, exposure in found.items()}
    events = []
    for asset_id, asset_changes in by_asset.items():
        asset = _asset_data(assets[asset_id])
        plain = [_change_data(c) for c in asset_changes if c.kind not in _EXPOSURE_EVENTS]
        if plain:
            created = any(c.kind == AssetChange.Kind.CREATED for c in asset_changes)
            event = "asset.created" if created else "asset.changed"
            events.append((event, {"asset": asset, "changes": plain}))
        events += [
            (_EXPOSURE_EVENTS[c.kind], {"asset": asset, "exposure": exposures[c.new_value["exposure_id"]]})
            for c in asset_changes
            if c.kind in _EXPOSURE_EVENTS
        ]
    return events


def publish_changes(org: Org, changes: Sequence[AssetChange]) -> list[OutboxEvent]:
    hooks = _enabled_hooks(org)
    if not hooks or not changes:
        return []
    rows = [row for event, data in group_changes(org, changes) for row in _rows(org, hooks, event, data)]
    return OutboxEvent.objects.bulk_create(rows, batch_size=500)
