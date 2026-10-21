"""Exposure rules (docs/architecture.md §4.6): pure functions asset -> hits.

Rules read ``services`` and ``links_out`` prefetched by ``evaluate_assets``
and never write. A hit's ``subject`` ("8443/tcp", a CNAME target) lets one
asset hold several open exposures of the same rule.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from atlas.assets.models import Asset, AssetLink, AssetService
from atlas.core import clock
from atlas.core.models import Org
from atlas.core.normalize import NormalizationError, is_public_ip
from atlas.exposure.models import Exposure

Severity = Exposure.Severity

# Matched against "service product banner" of an open port, lower-cased.
# "admin" also covers phpmyadmin, pgadmin, wp-admin and "administration".
_ADMIN_UI = re.compile(
    r"admin|webmin|cpanel|plesk|kibana|grafana|jenkins|portainer|tomcat manager"
    r"|rabbitmq management|kubernetes dashboard"
)


@dataclass(frozen=True)
class RuleContext:
    org: Org
    now: datetime
    today: date  # clock.local_date(org.timezone, now): "today" for the customer

    @classmethod
    def for_org(cls, org: Org, now: datetime | None = None) -> RuleContext:
        now = now or clock.now()
        return cls(org=org, now=now, today=clock.local_date(org.timezone, now))


@dataclass(frozen=True)
class Hit:
    subject: str
    severity: str
    title: str
    details: dict = field(default_factory=dict)


def _exposed_services(asset: Asset) -> list[AssetService]:
    """Open services of a public ``ip`` asset, by port; [] for anything else."""
    try:
        if asset.kind != Asset.Kind.IP or not is_public_ip(asset.key):
            return []
    except NormalizationError:
        return []
    services = [s for s in asset.services.all() if s.closed_at is None]
    return sorted(services, key=lambda s: (s.port, s.protocol))


def _port_hit(svc: AssetService, severity: str, title: str, **details) -> Hit:
    base = {"port": svc.port, "protocol": svc.protocol, "service": svc.service, "product": svc.product}
    return Hit(subject=f"{svc.port}/{svc.protocol}", severity=severity, title=title, details=base | details)


def admin_panel_public(asset: Asset, ctx: RuleContext) -> list[Hit]:
    return [
        _port_hit(svc, Severity.HIGH, f"Admin UI exposed on {asset.key}:{svc.port}")
        for svc in _exposed_services(asset)
        if _ADMIN_UI.search(f"{svc.service} {svc.product} {svc.banner}".lower())
    ]


def unexpected_port(asset: Asset, ctx: RuleContext) -> list[Hit]:
    allowed = sorted({int(port) for port in ctx.org.allowed_ports or []})
    return [
        _port_hit(svc, Severity.MEDIUM, f"Unexpected open port {svc.port}/{svc.protocol} on {asset.key}",
                  allowed_ports=allowed)
        for svc in _exposed_services(asset)
        if svc.port not in allowed
    ]


def cert_expiring(asset: Asset, ctx: RuleContext) -> list[Hit]:
    if asset.kind != Asset.Kind.CERTIFICATE:
        return []
    try:
        not_after = datetime.fromisoformat(asset.attributes["not_after"])
    except (KeyError, TypeError, ValueError):
        return []
    if not_after.tzinfo is None:  # attributes carry an offset; naive means a broken import
        return []
    # Both sides are calendar dates in the org's timezone, so "expires in 0 days"
    # means "on the customer's today", whatever the UTC date is.
    expires_on = clock.local_date(ctx.org.timezone, not_after)
    days_left = (expires_on - ctx.today).days
    if days_left > ctx.org.cert_warning_days:
        return []
    expired = not_after <= ctx.now
    name = asset.attributes.get("subject_cn") or asset.label or asset.key
    return [Hit(
        subject="",
        severity=Severity.CRITICAL if expired else Severity.MEDIUM,
        title=f"Certificate {name} {'expired' if expired else 'expires'} on {expires_on.isoformat()}",
        details={"not_after": clock.isoformat(not_after), "expires_on": expires_on.isoformat(),
                 "days_left": days_left, "warning_days": ctx.org.cert_warning_days},
    )]


def dangling_cname(asset: Asset, ctx: RuleContext) -> list[Hit]:
    if asset.kind != Asset.Kind.HOST:
        return []
    resolving = {AssetLink.Relation.RESOLVES_TO, AssetLink.Relation.CNAME}
    targets = [link.target for link in asset.links_out.all() if link.relation == AssetLink.Relation.CNAME]
    return [
        Hit(
            subject=target.key,
            severity=Severity.HIGH,
            title=f"{asset.key} is a CNAME to {target.key}, which resolves nowhere in the inventory",
            details={"target": target.key, "target_asset_id": target.id},
        )
        for target in targets
        if not any(out.relation in resolving for out in target.links_out.all())
    ]


RULES: dict[str, Callable[[Asset, RuleContext], list[Hit]]] = {
    Exposure.Rule.ADMIN_PANEL_PUBLIC: admin_panel_public,
    Exposure.Rule.CERT_EXPIRING: cert_expiring,
    Exposure.Rule.DANGLING_CNAME: dangling_cname,
    Exposure.Rule.UNEXPECTED_PORT: unexpected_port,
}
