from datetime import UTC, datetime

import pytest

from atlas.assets.models import Asset, AssetChange
from atlas.core import clock
from atlas.exposure.models import Exposure
from atlas.exposure.service import evaluate_assets
from tests.factories import TODAY, make_asset, make_job, make_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def ip(org):
    asset = make_asset(org, Asset.Kind.IP, key="198.51.100.20")
    make_service(asset, 443)
    make_service(asset, 8080, product="Grafana")
    return asset


def open_rules(asset):
    return sorted(Exposure.objects.filter(asset=asset, status="open").values_list("rule", "subject"))


def test_opens_exposures_with_history_rows(org, ip):
    job = make_job(org)
    result = evaluate_assets(org, [ip.id], job=job)
    assert open_rules(ip) == [("admin_panel_public", "8080/tcp"), ("unexpected_port", "8080/tcp")]
    assert result.evaluated == 1 and len(result.opened) == 2 and result.resolved == []
    change = AssetChange.objects.get(asset=ip, field="admin_panel_public")
    assert (change.kind, change.job, change.occurred_at) == ("exposure_opened", job, TODAY)
    exposure = Exposure.objects.get(asset=ip, rule="admin_panel_public")
    assert change.new_value == {"exposure_id": exposure.id, "subject": "8080/tcp", "severity": "high"}


def test_reevaluation_is_idempotent_and_refreshes(org, ip, frozen_clock):
    evaluate_assets(org, [ip.id])
    frozen_clock.advance(hours=6)
    result = evaluate_assets(org, [ip.id])
    assert result.opened == result.resolved == result.changes == []
    assert Exposure.objects.filter(asset=ip).count() == 2
    assert set(Exposure.objects.values_list("last_evaluated_at", flat=True)) == {clock.now()}


def test_resolves_when_the_hit_goes_away_and_reopens_as_a_new_row(org, ip, frozen_clock):
    evaluate_assets(org, [ip.id])
    ip.services.filter(port=8080).update(closed_at=TODAY)
    frozen_clock.advance(hours=1)
    result = evaluate_assets(org, [ip.id])
    assert sorted(e.rule for e in result.resolved) == ["admin_panel_public", "unexpected_port"]
    assert {c.kind for c in result.changes} == {"exposure_resolved"}
    assert open_rules(ip) == []
    assert set(Exposure.objects.values_list("resolved_at", flat=True)) == {clock.now()}
    ip.services.filter(port=8080).update(closed_at=None)
    evaluate_assets(org, [ip.id])
    assert Exposure.objects.filter(asset=ip, rule="unexpected_port").count() == 2
    assert len(open_rules(ip)) == 2


def test_archived_assets_get_their_exposures_resolved(org, ip):
    evaluate_assets(org, [ip.id])
    Asset.objects.filter(pk=ip.pk).update(archived_at=TODAY)
    assert len(evaluate_assets(org).resolved) == 2
    assert open_rules(ip) == []


def test_certificate_severity_is_refreshed_in_place(org, frozen_clock):
    asset = make_asset(org, Asset.Kind.CERTIFICATE, key="ef" * 32,
                       attributes={"not_after": "2026-11-10T00:00:00Z", "subject_cn": "vpn.harborview"})
    evaluate_assets(org, [asset.id])
    frozen_clock.freeze(datetime(2026, 11, 10, 6, 0, tzinfo=UTC))
    result = evaluate_assets(org, [asset.id])
    exposure = Exposure.objects.get(asset=asset)
    assert (exposure.severity, exposure.status, result.changes) == ("critical", "open", [])
    assert "expired on 2026-11-09" in exposure.title  # 19:00 on Nov 9 in Toronto


def test_ignores_assets_of_other_orgs(org, other_org, ip):
    foreign = make_asset(other_org, Asset.Kind.IP, key="203.0.113.99")
    make_service(foreign, 23)
    result = evaluate_assets(org, [ip.id, foreign.id])
    assert result.evaluated == 1
    assert not Exposure.objects.filter(asset=foreign).exists()
