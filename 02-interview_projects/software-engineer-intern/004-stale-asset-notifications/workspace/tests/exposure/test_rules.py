from datetime import UTC, datetime

import pytest

from atlas.assets.models import Asset, AssetLink
from atlas.core import clock
from atlas.exposure.rules import RULES, RuleContext
from tests.factories import TODAY, make_asset, make_link, make_service

pytestmark = pytest.mark.django_db


def hits(rule, asset):
    asset = Asset.objects.prefetch_related("services", "links_out__target__links_out").get(pk=asset.pk)
    return RULES[rule](asset, RuleContext.for_org(asset.org))


def cert(org, not_after: datetime):
    return make_asset(org, Asset.Kind.CERTIFICATE, key="ab" * 32, attributes={
        "subject_cn": "www.harborview-bank.example.test", "not_after": clock.isoformat(not_after)})


def test_unexpected_port_flags_public_ports_outside_the_org_allow_list(org):
    ip = make_asset(org, Asset.Kind.IP, key="198.51.100.7")
    make_service(ip, 443)
    make_service(ip, 22, product="OpenSSH")
    make_service(ip, 3389, closed_at=TODAY)
    [hit] = hits("unexpected_port", ip)
    assert (hit.subject, hit.severity, hit.details["allowed_ports"]) == ("22/tcp", "medium", [443])


def test_port_rules_ignore_internal_addresses(org):
    ip = make_asset(org, Asset.Kind.IP, key="10.0.4.2")
    make_service(ip, 8080, product="Jenkins")
    assert hits("unexpected_port", ip) == [] and hits("admin_panel_public", ip) == []


@pytest.mark.parametrize(("fields", "expected"), [
    ({"product": "Jenkins"}, ["8443/tcp"]),
    ({"service": "http", "banner": "<title>phpMyAdmin</title>"}, ["8443/tcp"]),
    ({"service": "https", "product": "nginx"}, []),
])
def test_admin_panel_public(org, fields, expected):
    ip = make_asset(org, Asset.Kind.IP, key="203.0.113.10")
    make_service(ip, 8443, **fields)
    found = hits("admin_panel_public", ip)
    assert [h.subject for h in found] == expected
    assert all(h.severity == "high" for h in found)


@pytest.mark.parametrize(("not_after", "severity", "days_left"), [
    (datetime(2026, 12, 5, 15, 0, tzinfo=UTC), "medium", 30),  # boundary: 30 days still warns
    (datetime(2026, 12, 6, 15, 0, tzinfo=UTC), None, 31),
    (datetime(2026, 11, 5, 20, 0, tzinfo=UTC), "medium", 0),  # later today
    (datetime(2026, 11, 5, 14, 0, tzinfo=UTC), "critical", 0),  # half an hour ago
    (datetime(2026, 10, 1, tzinfo=UTC), "critical", -36),
])
def test_cert_expiring_window_and_severity(org, not_after, severity, days_left):
    found = [(h.severity, h.details["days_left"]) for h in hits("cert_expiring", cert(org, not_after))]
    assert found == ([(severity, days_left)] if severity else [])


def test_cert_expiring_counts_days_in_the_org_timezone(org, frozen_clock):
    # 22:00 on Nov 5 in Toronto, already Nov 6 in UTC; Dec 6 07:00 Toronto is 31 local days away.
    frozen_clock.freeze(datetime(2026, 11, 6, 3, 0, tzinfo=UTC))
    asset = cert(org, datetime(2026, 12, 6, 12, 0, tzinfo=UTC))
    assert hits("cert_expiring", asset) == []
    org.timezone = "UTC"
    org.save()
    assert [h.details["days_left"] for h in hits("cert_expiring", asset)] == [30]


def test_cert_without_usable_expiry_is_skipped(org):
    asset = make_asset(org, Asset.Kind.CERTIFICATE, key="cd" * 32, attributes={"not_after": "soon"})
    assert hits("cert_expiring", asset) == []


def test_dangling_cname_flags_targets_that_resolve_nowhere(org):
    host = make_asset(org, key="shop.harborview-bank.example.test")
    dangling = make_asset(org, key="hv-shop.storefront.example.test")
    resolved = make_asset(org, key="cdn.harborview-bank.example.test")
    chained = make_asset(org, key="alias.harborview-bank.example.test")
    make_link(resolved, make_asset(org, Asset.Kind.IP, key="192.0.2.8"))
    make_link(chained, resolved, AssetLink.Relation.CNAME)
    for target in (dangling, resolved, chained):
        make_link(host, target, AssetLink.Relation.CNAME)
    [hit] = hits("dangling_cname", host)
    assert (hit.subject, hit.severity) == ("hv-shop.storefront.example.test", "high")
    assert hits("dangling_cname", dangling) == []

