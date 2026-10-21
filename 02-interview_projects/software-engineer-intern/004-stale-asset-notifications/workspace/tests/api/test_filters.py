from datetime import timedelta

import pytest
from django.http import QueryDict

from atlas.assets.filters import InvalidFilter, canonical_querystring, filter_assets
from atlas.assets.models import Asset
from tests.api.helpers import keys
from tests.factories import TODAY, make_asset, make_change, make_exposure, make_tag

pytestmark = pytest.mark.django_db


def _keys(org, query: str) -> list[str]:
    return sorted(filter_assets(Asset.objects.all(), QueryDict(query), org=org).values_list("key", flat=True))


@pytest.fixture
def inventory(org, other_org):
    www = make_asset(org, key="www.harborview-bank.example.test", label="Public Website", owner_team="web")
    api = make_asset(org, key="api.harborview-bank.example.test", label="API gateway")
    ip = make_asset(org, kind="ip", key="198.51.100.7", owner_team="sre")
    prod, edge = make_tag(org, "prod"), make_tag(org, "edge")
    www.tags.add(prod, edge)
    api.tags.add(prod)
    make_exposure(ip, subject="8443/tcp")
    make_exposure(ip, rule="admin_panel_public", subject="8443/tcp", severity="high")
    make_exposure(api, rule="dangling_cname", status="resolved")
    make_asset(org, key="old.harborview-bank.example.test", archived_at=TODAY)
    make_asset(other_org, key="www.quillstone-media.example.test")
    return {"www": www, "api": api, "ip": ip}


def test_kind_is_any_of_and_tag_is_all_of(org, inventory):
    assert _keys(org, "kind=ip&kind=host") == ["198.51.100.7", "api.harborview-bank.example.test",
                                               "www.harborview-bank.example.test"]
    assert _keys(org, "tag=prod") == ["api.harborview-bank.example.test", "www.harborview-bank.example.test"]
    assert _keys(org, "tag=prod&tag=edge") == ["www.harborview-bank.example.test"]


def test_owner_and_unowned(org, inventory):
    assert _keys(org, "owner=web") == ["www.harborview-bank.example.test"]
    assert _keys(org, "owner=-") == ["api.harborview-bank.example.test"]


def test_exposure_counts_open_ones_only_without_duplicates(org, inventory):
    assert _keys(org, "exposure=any") == ["198.51.100.7"]
    assert _keys(org, "exposure=dangling_cname") == []
    assert _keys(org, "exposure=unexpected_port&exposure=admin_panel_public") == ["198.51.100.7"]


def test_q_matches_key_or_label_case_insensitively(org, inventory):
    assert _keys(org, "q=WEBSITE") == ["www.harborview-bank.example.test"]
    assert _keys(org, "q=api.harbor") == ["api.harborview-bank.example.test"]


def test_archived_hidden_unless_asked(org, inventory):
    assert "old.harborview-bank.example.test" not in _keys(org, "")
    assert "old.harborview-bank.example.test" in _keys(org, "include_archived=1")
    with pytest.raises(InvalidFilter):
        _keys(org, "include_archived=maybe")


def test_changed_since_needs_an_offset(org, inventory):
    make_change(inventory["www"], occurred_at=TODAY - timedelta(hours=3))
    make_change(inventory["api"], occurred_at=TODAY - timedelta(days=3))
    assert _keys(org, "changed_since=2026-11-05T05:30:00-05:00") == ["www.harborview-bank.example.test"]
    assert _keys(org, "changed_since=2026-11-01T00:00:00Z") == ["api.harborview-bank.example.test",
                                                               "www.harborview-bank.example.test"]
    with pytest.raises(InvalidFilter) as error:
        _keys(org, "changed_since=2026-11-05T05:30:00")
    assert error.value.param == "changed_since"


def test_changed_within_uses_the_notify_window(org, inventory, window_start_calls):
    make_change(inventory["www"], occurred_at=TODAY - timedelta(hours=23))
    make_change(inventory["api"], occurred_at=TODAY - timedelta(hours=25))
    assert _keys(org, "changed_within=24") == ["www.harborview-bank.example.test"]
    assert window_start_calls == [("harborview-bank", 24)]
    for bad in ("0", "1.5", "day"):
        with pytest.raises(InvalidFilter):
            _keys(org, f"changed_within={bad}")


def test_other_orgs_rows_never_leak(org, other_org, inventory):
    foreign_tag = make_tag(other_org, "prod")
    theirs = Asset.objects.get(org=other_org)
    theirs.tags.add(foreign_tag)
    make_exposure(theirs)
    assert "www.quillstone-media.example.test" not in _keys(org, "tag=prod")
    assert _keys(org, "exposure=any") == ["198.51.100.7"]


def test_unknown_values_are_rejected(org):
    with pytest.raises(InvalidFilter) as error:
        _keys(org, "kind=vm")
    assert error.value.param == "kind"
    with pytest.raises(InvalidFilter):
        _keys(org, "exposure=weak_tls")


def test_canonical_querystring():
    params = QueryDict("tag=prod&kind=ip&cursor=abc&tag=edge&q=&kind=host&q=pay+ments&kind=ip")
    assert canonical_querystring(params) == "kind=host&kind=ip&q=pay+ments&tag=edge&tag=prod"
    assert canonical_querystring({"owner": ["-"], "changed_since": ["2026-11-05T09:30:00-05:00"]}) == (
        "changed_since=2026-11-05T09%3A30%3A00-05%3A00&owner=-")


def test_api_reports_invalid_filters(api_client, org, inventory):
    response = api_client.get("/api/v1/assets/", {"changed_since": "2026-11-05 09:30"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_failed" and list(error["details"]) == ["changed_since"]
    assert keys(api_client.get("/api/v1/assets/", {"kind": "ip", "exposure": "any"})) == ["198.51.100.7"]
