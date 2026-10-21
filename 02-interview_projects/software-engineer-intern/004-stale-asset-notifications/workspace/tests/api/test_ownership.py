import pytest

from atlas.assets.models import AssetChange
from atlas.assets.ownership import apply_ownership, matching_rule
from tests.factories import make_asset, make_job, make_rule, make_tag

pytestmark = pytest.mark.django_db
URL = "/api/v1/ownership-rules/"


def test_priority_beats_specificity_and_ties_go_to_the_older_rule(org):
    host = make_asset(org, key="pay.eu.harborview-bank.example.test")
    narrow = make_rule(org, "pay.eu.harborview-bank.example.test", "payments", priority=50)
    broad = make_rule(org, "*.harborview-bank.example.test", "web-platform", priority=10)
    twin = make_rule(org, "*.eu.harborview-bank.example.test", "eu-ops", priority=10)
    assert matching_rule(host, [narrow, twin, broad]) == broad
    broad.enabled = False
    assert matching_rule(host, [narrow, twin, broad]) == twin


def test_hostname_glob_crosses_dots_and_skips_other_kinds(org):
    rule = make_rule(org, "*.harborview-bank.example.test", "web")
    assert matching_rule(make_asset(org, key="a.b.harborview-bank.example.test"), [rule]) == rule
    assert matching_rule(make_asset(org, kind="domain", key="x.harborview-bank.example.test"), [rule]) == rule
    cloud = make_asset(org, kind="cloud_resource", key="nimbus:1:vm.harborview-bank.example.test")
    assert matching_rule(cloud, [rule]) is None


def test_cidr_matches_contained_ips_and_networks(org):
    rule = make_rule(org, "198.51.100.0/24", "network-team", pattern_type="cidr")
    assert matching_rule(make_asset(org, kind="ip", key="198.51.100.9"), [rule]) == rule
    assert matching_rule(make_asset(org, kind="network", key="198.51.100.128/25"), [rule]) == rule
    assert matching_rule(make_asset(org, kind="network", key="198.51.0.0/16"), [rule]) is None
    assert matching_rule(make_asset(org, kind="ip", key="2001:db8::1"), [rule]) is None


def test_tag_rule(org):
    asset = make_asset(org)
    rule = make_rule(org, "pci", "compliance", pattern_type="tag")
    assert matching_rule(asset, [rule]) is None
    asset.tags.add(make_tag(org, "pci"))
    assert matching_rule(asset, [rule]) == rule


def test_apply_sets_clears_and_skips_locked(org, other_org):
    make_rule(org, "*.harborview-bank.example.test", "web")
    matched = make_asset(org, key="www.harborview-bank.example.test")
    orphan = make_asset(org, key="legacy.example.test", owner_team="web")
    locked = make_asset(org, key="vpn.harborview-bank.example.test", owner_team="netsec", owner_locked=True)
    theirs = make_asset(other_org, key="www.harborview-bank.example.test")
    job = make_job(org)
    changes = apply_ownership(org, job=job)
    assert {(c.asset_id, c.old_value, c.new_value) for c in changes} == {(matched.id, "", "web"),
                                                                         (orphan.id, "web", "")}
    assert all(c.kind == AssetChange.Kind.OWNER_CHANGED and c.job == job for c in changes)
    for asset in (matched, orphan, locked, theirs):
        asset.refresh_from_db()
    owners = [asset.owner_team for asset in (matched, orphan, locked, theirs)]
    assert owners == ["web", "", "netsec", ""]
    assert apply_ownership(org) == []


def test_apply_limited_to_asset_ids(org):
    make_rule(org, "*", "everyone")
    first, second = make_asset(org), make_asset(org)
    assert [c.asset_id for c in apply_ownership(org, [second.id])] == [second.id]
    first.refresh_from_db()
    assert first.owner_team == ""


def test_rules_api_normalizes_patterns(api_client, org):
    pattern = "*.Bücher.Harborview-Bank.example.test."
    body = {"pattern_type": "hostname", "pattern": pattern, "team": "books", "priority": 5}
    created = api_client.post(URL, body, format="json")
    assert created.status_code == 201, created.content
    assert created.json()["pattern"] == "*.xn--bcher-kva.harborview-bank.example.test"
    cidr = api_client.post(URL, {"pattern_type": "cidr", "pattern": "10.1.2.3/16", "team": "net"},
                           format="json")
    assert cidr.json()["pattern"] == "10.1.0.0/16" and cidr.json()["priority"] == 100
    bad = api_client.post(URL, {"pattern_type": "cidr", "pattern": "10.1.2/33", "team": "net"}, format="json")
    assert bad.status_code == 400 and list(bad.json()["error"]["details"]) == ["pattern"]
    changed = api_client.patch(f"{URL}{cidr.json()['id']}/", {"pattern_type": "tag"}, format="json")
    assert changed.status_code == 400
    listed = api_client.get(URL).json()
    assert [r["team"] for r in listed] == ["books", "net"]


def test_rules_api_apply_and_scoping(api_client, org, other_org):
    asset = make_asset(org, key="www.harborview-bank.example.test")
    make_rule(org, "www.*", "web")
    theirs = make_rule(other_org, "*", "quill")
    response = api_client.post(f"{URL}apply/")
    assert response.status_code == 200 and response.json() == {"changed": 1}
    asset.refresh_from_db()
    assert asset.owner_team == "web"
    assert api_client.patch(f"{URL}{theirs.id}/", {"team": "mine"}, format="json").status_code == 404
    assert api_client.delete(f"{URL}{theirs.id}/").status_code == 404
