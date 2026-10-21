"""Ownership rules: which team owns an asset.

Enabled rules are tried in ``(priority, id)`` order (lower priority first,
the older rule on a tie) and the first match wins; specificity plays no part,
so a broad rule with a low number beats a narrow one with a higher number.

* ``hostname``: ``fnmatch.fnmatchcase(asset.key, pattern)`` on ``host`` and
  ``domain`` assets. ``*`` crosses dots: ``*.harborview-bank.example.test``
  also matches ``a.b.harborview-bank.example.test``.
* ``cidr``: ``ip`` assets inside the network, ``network`` assets contained
  in it (same IP version).
* ``tag``: the asset carries the tag.

Assets whose owner was set by hand (``owner_locked``) are left alone. An
asset no rule matches ends up unowned (``owner_team = ""``).
"""

from __future__ import annotations

import fnmatch
import ipaddress
from collections.abc import Iterable, Sequence

from atlas.assets.models import Asset, AssetChange, OwnershipRule
from atlas.core import clock
from atlas.core.models import Org
from atlas.jobs.models import Job

_HOSTNAME_KINDS = {Asset.Kind.HOST, Asset.Kind.DOMAIN}


def _ordered(rules: Iterable[OwnershipRule]) -> list[OwnershipRule]:
    return sorted((rule for rule in rules if rule.enabled), key=lambda rule: (rule.priority, rule.id))


def _network(text: str):
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError:
        return None


def _matches(rule: OwnershipRule, asset: Asset, tag_names: set[str]) -> bool:
    if rule.pattern_type == OwnershipRule.PatternType.HOSTNAME:
        return asset.kind in _HOSTNAME_KINDS and fnmatch.fnmatchcase(asset.key, rule.pattern)
    if rule.pattern_type == OwnershipRule.PatternType.TAG:
        return rule.pattern in tag_names
    if rule.pattern_type == OwnershipRule.PatternType.CIDR:
        if asset.kind not in (Asset.Kind.IP, Asset.Kind.NETWORK):
            return False
        network, candidate = _network(rule.pattern), _network(asset.key)
        if network is None or candidate is None or network.version != candidate.version:
            return False
        return candidate.subnet_of(network)
    return False


def _tag_names(asset: Asset) -> set[str]:
    return {tag.name for tag in asset.tags.all()}


def matching_rule(asset: Asset, rules: Sequence[OwnershipRule]) -> OwnershipRule | None:
    """The rule that decides ``asset``'s owner, or None; ``rules`` may come in any order."""
    tag_names = _tag_names(asset)
    return next((rule for rule in _ordered(rules) if _matches(rule, asset, tag_names)), None)


def apply_ownership(
    org: Org, asset_ids: Iterable[int] | None = None, *, job: Job | None = None
) -> list[AssetChange]:
    """Re-evaluate owners of ``asset_ids`` (None = every asset of the org).

    Writes one ``owner_changed`` change per asset whose owner moved and
    returns them. Runs inside the caller's transaction.
    """
    rules = _ordered(OwnershipRule.objects.for_org(org))
    assets = Asset.objects.for_org(org).filter(owner_locked=False).prefetch_related("tags").order_by("id")
    if asset_ids is not None:
        assets = assets.filter(id__in=list(asset_ids))

    now = clock.now()
    changed: list[Asset] = []
    changes: list[AssetChange] = []
    for asset in assets.iterator(chunk_size=2000):
        tag_names = _tag_names(asset)
        rule = next((r for r in rules if _matches(r, asset, tag_names)), None)
        team = rule.team if rule is not None else ""
        if team == asset.owner_team:
            continue
        changes.append(
            AssetChange(
                org=org, asset=asset, kind=AssetChange.Kind.OWNER_CHANGED, field="owner_team",
                old_value=asset.owner_team, new_value=team, job=job, occurred_at=now,
                source_kind="ownership_rule",
            )
        )
        asset.owner_team, asset.updated_at = team, now
        changed.append(asset)

    Asset.objects.bulk_update(changed, ["owner_team", "updated_at"], batch_size=1000)
    return AssetChange.objects.bulk_create(changes, batch_size=1000)
