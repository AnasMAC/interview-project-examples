"""Plain factory functions for tests. Every helper saves and returns the row.

Defaults match docs/architecture.md: tests run at 2026-11-05 09:30 -05:00 and
use the three demo orgs below. Keyword arguments override any model field.
"""

import itertools
from datetime import UTC, datetime

from django.contrib.auth import get_user_model

from atlas.assets.models import (
    Asset,
    AssetChange,
    AssetLink,
    AssetService,
    AssetSource,
    OwnershipRule,
    SavedView,
    Tag,
)
from atlas.core.auth import issue_api_key
from atlas.core.models import Membership, Org
from atlas.exposure.models import Exposure
from atlas.jobs.models import Job
from atlas.notify.models import EVENTS, OutboxEvent, Webhook

TODAY = datetime(2026, 11, 5, 14, 30, tzinfo=UTC)  # 09:30 America/Toronto
ORGS = {
    "harborview-bank": ("Harborview Bank", "America/Toronto", [443]),
    "quillstone-media": ("Quillstone Media", "Europe/London", [80, 443]),
    "orchid-grid": ("Orchid Grid", "Pacific/Auckland", [22, 443, 8443]),
}
_seq = itertools.count(1)


def make_org(slug: str = "harborview-bank", **fields) -> Org:
    name, tz, ports = ORGS.get(slug, (slug.replace("-", " ").title(), "UTC", [80, 443]))
    defaults = {"name": name, "domain": f"{slug}.example.test", "timezone": tz, "allowed_ports": ports}
    return Org.objects.create(slug=slug, **(defaults | fields))


def make_api_key(org: Org, name: str = "ci", raw: str | None = None):
    """Returns (ApiKey, raw key)."""
    return issue_api_key(org, name, raw=raw)


def make_user(username: str = "", orgs=(), password: str = "DEMO-pass", **fields):
    user = get_user_model().objects.create_user(username or f"user{next(_seq)}", password=password, **fields)
    for org in orgs:
        Membership.objects.create(user=user, org=org)
    return user


def make_asset(org: Org, kind: str = Asset.Kind.HOST, key: str = "", **fields) -> Asset:
    if key == "":
        n = next(_seq)
        key = {"ip": f"198.51.100.{n % 250 + 1}", "network": f"10.{n % 250}.0.0/16"}.get(
            kind, f"h{n}.{org.domain}"
        )
    return Asset.objects.create(org=org, kind=kind, key=key, label=fields.pop("label", key), **fields)


def make_source(asset: Asset, source_kind: str = AssetSource.Kind.ZONE_FILE, source_name: str = "", **fields):
    name = source_name or f"{asset.org.domain} zone"
    return AssetSource.objects.create(asset=asset, source_kind=source_kind, source_name=name, **fields)


def make_link(asset: Asset, target: Asset, relation: str = AssetLink.Relation.RESOLVES_TO, **fields):
    fields.setdefault("source_kind", AssetSource.Kind.ZONE_FILE)
    return AssetLink.objects.create(asset=asset, target=target, relation=relation, **fields)


def make_service(asset: Asset, port: int = 443, protocol: str = "tcp", **fields) -> AssetService:
    return AssetService.objects.create(asset=asset, port=port, protocol=protocol, **fields)


def make_tag(org: Org, name: str = "", **fields) -> Tag:
    return Tag.objects.create(org=org, name=name or f"tag-{next(_seq)}", **fields)


def make_rule(org: Org, pattern: str, team: str, pattern_type: str = "hostname", **fields):
    return OwnershipRule.objects.create(
        org=org, pattern=pattern, team=team, pattern_type=pattern_type, **fields
    )


def make_change(asset: Asset, kind: str = AssetChange.Kind.CREATED, **fields) -> AssetChange:
    return AssetChange.objects.create(org=asset.org, asset=asset, kind=kind, **fields)


def make_exposure(asset: Asset, rule: str = Exposure.Rule.UNEXPECTED_PORT, **fields) -> Exposure:
    defaults = {"severity": Exposure.Severity.MEDIUM, "title": f"{rule} on {asset.key}"}
    return Exposure.objects.create(org=asset.org, asset=asset, rule=rule, **(defaults | fields))


def make_webhook(org: Org, url: str = "", events=None, **fields) -> Webhook:
    return Webhook.objects.create(
        org=org,
        name=fields.pop("name", f"hook-{next(_seq)}"),
        url=url or f"http://mockhook:9000/hooks/{org.slug}",
        secret=fields.pop("secret", f"DEMO-whsec-{org.slug}"),
        events=list(EVENTS) if events is None else events,
        **fields,
    )


def make_outbox(webhook: Webhook, event: str = "asset.created", payload=None, **fields):
    return OutboxEvent.objects.create(
        org=webhook.org, webhook=webhook, event=event, payload=payload or {}, **fields
    )


def make_job(org: Org, kind: str = "import.run", payload=None, **fields) -> Job:
    return Job.objects.create(org=org, kind=kind, payload=payload or {}, **fields)


def make_saved_view(org: Org, name: str = "", querystring: str = "kind=host", **fields):
    return SavedView.objects.create(
        org=org, name=name or f"view-{next(_seq)}", querystring=querystring, **fields
    )
