from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from atlas.assets.models import Asset, AssetChange
from atlas.importers.base import ImportBatch, Observation
from atlas.merge.identity import identity_key
from atlas.merge.service import merge_batch
from tests.api.helpers import keys, results
from tests.factories import (
    TODAY,
    make_asset,
    make_change,
    make_exposure,
    make_link,
    make_rule,
    make_service,
    make_source,
    make_tag,
)

pytestmark = pytest.mark.django_db
URL = "/api/v1/assets/"


def _changes(asset_id):
    return list(AssetChange.objects.filter(asset_id=asset_id).order_by("id").values_list("kind", "field"))


def test_requires_an_api_key(client, org):
    response = client.get(URL)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_list_shape_counts_only_open_exposures(api_client, org):
    asset = make_asset(org, key="www.harborview-bank.example.test")
    asset.tags.add(make_tag(org, "prod"), make_tag(org, "edge"))
    make_exposure(asset)
    make_exposure(asset, rule="dangling_cname", status="resolved")
    body = api_client.get(URL).json()
    assert set(body) == {"next", "previous", "results"}
    row = body["results"][0]
    assert row["tags"] == ["edge", "prod"] and row["open_exposures"] == 1
    assert row["last_seen_at"] == "2026-11-05T14:30:00Z"
    assert set(row) == {"id", "kind", "key", "label", "owner_team", "owner_locked", "tags", "attributes",
                        "first_seen_at", "last_seen_at", "archived_at", "open_exposures"}


def test_cursor_pages_break_ties_on_id(api_client, org):
    same = [make_asset(org, key=f"s{i}.harborview-bank.example.test") for i in range(3)]
    newest = make_asset(org, key="new.harborview-bank.example.test", last_seen_at=TODAY + timedelta(hours=1))
    first = api_client.get(URL, {"page_size": 2}).json()
    assert [r["id"] for r in first["results"]] == [newest.id, same[2].id]
    second = api_client.get(first["next"]).json()
    assert [r["id"] for r in second["results"]] == [same[1].id, same[0].id]
    assert second["next"] is None


def test_list_queries_do_not_grow_with_rows(api_client, org):
    def count():
        with CaptureQueriesContext(connection) as queries:
            assert api_client.get(URL).status_code == 200
        return len(queries)

    tag = make_tag(org, "prod")
    make_asset(org).tags.add(tag)
    count()  # first request also stamps ApiKey.last_used_at
    baseline = count()
    for _ in range(10):
        asset = make_asset(org)
        asset.tags.add(tag)
        make_exposure(asset)
    assert count() == baseline


def test_page_size_is_capped(api_client, org):
    Asset.objects.bulk_create(Asset(org=org, kind="host", key=f"b{i}.example.test", label="b")
                              for i in range(505))
    assert len(results(api_client.get(URL, {"page_size": 1000}))) == 500
    assert len(results(api_client.get(URL))) == 50


def test_create_normalizes_key_and_records_history(api_client, org):
    make_rule(org, "*.harborview-bank.example.test", "web-platform")
    response = api_client.post(URL, {"kind": "host", "key": " WWW.Harborview-Bank.Example.Test. ",
                                     "tags": ["Prod", "prod", "edge"]}, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["key"] == "www.harborview-bank.example.test" and body["label"] == body["key"]
    assert body["tags"] == ["edge", "prod"] and body["owner_team"] == "web-platform"
    assert body["sources"][0]["source_kind"] == "api" and body["sources"][0]["source_name"] == "api key ci"
    assert _changes(body["id"]) == [("created", ""), ("source_added", "api"), ("tagged", "tags"),
                                    ("tagged", "tags"), ("owner_changed", "owner_team")]


@pytest.mark.parametrize(("kind", "key", "expected"), [
    ("ip", "2001:DB8:0:0::7", "2001:db8::7"),
    ("ip", "::ffff:198.51.100.7", "198.51.100.7"),
    ("network", "10.1.2.3/16", "10.1.0.0/16"),
    ("certificate", "AB:" * 31 + "AB", "ab" * 32),
    ("cloud_resource", "Nimbus:4471-2210-0093:VM-12", "nimbus:4471-2210-0093:vm-12"),
])
def test_create_normalizes_each_kind(api_client, org, kind, key, expected):
    response = api_client.post(URL, {"kind": kind, "key": key}, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["key"] == expected


def test_create_rejects_bad_keys_and_duplicates(api_client, org):
    bad = api_client.post(URL, {"kind": "ip", "key": "300.1.1.1"}, format="json")
    assert bad.status_code == 400 and list(bad.json()["error"]["details"]) == ["key"]
    make_asset(org, kind="ip", key="198.51.100.7")
    duplicate = api_client.post(URL, {"kind": "ip", "key": "::ffff:198.51.100.7"}, format="json")
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(("kind", "api_key", "imported"), [
    ("certificate", "C5:D6:" + "ab" * 30, "c5d6" + "AB" * 30),
    ("cloud_resource", " Nimbus:ACCT_7F3K:i-07E1/b ", "nimbus:acct_7f3k:I-07E1/B"),
    ("host", "Statements.Harborview-Bank.Example.Test.", "statements.harborview-bank.example.test"),
])
def test_api_keys_are_the_merge_identity_keys(api_client, org, kind, api_key, imported):
    created = api_client.post(URL, {"kind": kind, "key": api_key}, format="json")
    assert created.status_code == 201, created.content
    batch = ImportBatch(importer="nimbus", source_kind="nimbus", source_name="feed", observed_at=TODAY,
                        observations=[Observation(kind, imported)])
    merge_batch(org, batch)
    [asset] = Asset.objects.filter(org=org, kind=kind)
    assert asset.key == created.json()["key"] == identity_key(kind, imported)
    assert sorted(asset.sources.values_list("source_kind", flat=True)) == ["api", "nimbus"]


def test_a_host_named_like_an_existing_domain_is_a_conflict(api_client, org):
    make_asset(org, kind="domain", key="harborview-bank.example.test")
    response = api_client.post(URL, {"kind": "host", "key": "Harborview-Bank.example.test"}, format="json")
    assert response.status_code == 409 and "domain" in response.json()["error"]["message"]


def test_the_same_key_in_another_org_is_not_a_conflict(api_client, org, other_org):
    make_asset(other_org, kind="ip", key="198.51.100.7")
    assert api_client.post(URL, {"kind": "ip", "key": "198.51.100.7"}, format="json").status_code == 201


def test_detail_includes_sources_links_services_exposures(api_client, org):
    host = make_asset(org, key="api.harborview-bank.example.test")
    ip = make_asset(org, kind="ip", key="198.51.100.20")
    make_source(host)
    make_link(host, ip)
    make_service(ip, 8443)
    make_exposure(ip, subject="8443/tcp")
    host_body = api_client.get(f"{URL}{host.id}/").json()
    assert host_body["sources"][0]["source_kind"] == "zone_file"
    seen = "2026-11-05T14:30:00Z"
    assert host_body["links"] == [{"relation": "resolves_to", "direction": "out", "source_kind": "zone_file",
                                   "asset": {"id": ip.id, "kind": "ip", "key": "198.51.100.20"},
                                   "first_seen_at": seen, "last_seen_at": seen}]
    ip_body = api_client.get(f"{URL}{ip.id}/").json()
    assert ip_body["links"][0]["direction"] == "in" and ip_body["links"][0]["asset"]["id"] == host.id
    assert ip_body["services"][0]["port"] == 8443
    assert ip_body["exposures"][0]["subject"] == "8443/tcp" and ip_body["open_exposures"] == 1


def test_patch_owner_locks_and_empty_owner_returns_to_rules(api_client, org):
    make_rule(org, "*.harborview-bank.example.test", "web-platform")
    asset = make_asset(org, key="pay.harborview-bank.example.test", owner_team="web-platform")
    response = api_client.patch(f"{URL}{asset.id}/", {"owner_team": "payments", "label": "Payments"},
                                format="json")
    assert response.status_code == 200
    assert response.json()["owner_team"] == "payments" and response.json()["owner_locked"] is True
    response = api_client.patch(f"{URL}{asset.id}/", {"owner_team": ""}, format="json")
    assert response.json()["owner_team"] == "web-platform" and response.json()["owner_locked"] is False
    assert [c[0] for c in _changes(asset.id)] == ["updated", "owner_changed", "owner_changed"]


def test_patch_tags_replaces_the_set(api_client, org):
    asset = make_asset(org)
    asset.tags.add(make_tag(org, "old"))
    response = api_client.patch(f"{URL}{asset.id}/", {"tags": ["new"]}, format="json")
    assert response.json()["tags"] == ["new"]
    assert _changes(asset.id) == [("tagged", "tags"), ("untagged", "tags")]
    assert api_client.patch(f"{URL}{asset.id}/", {"tags": ["Not a slug"]}, format="json").status_code == 400


def test_put_is_not_allowed(api_client, org):
    asset = make_asset(org)
    response = api_client.put(f"{URL}{asset.id}/", {"label": "x"}, format="json")
    assert response.status_code == 405 and response.json()["error"]["code"] == "method_not_allowed"


def test_delete_archives(api_client, org):
    asset = make_asset(org)
    assert api_client.delete(f"{URL}{asset.id}/").status_code == 204
    assert api_client.delete(f"{URL}{asset.id}/").status_code == 204
    asset.refresh_from_db()
    assert asset.archived_at == TODAY and _changes(asset.id) == [("archived", "archived_at")]
    assert keys(api_client.get(URL)) == []
    assert keys(api_client.get(URL, {"include_archived": "1"})) == [asset.key]
    assert api_client.get(f"{URL}{asset.id}/").json()["archived_at"] == "2026-11-05T14:30:00Z"


def test_delete_resolves_open_exposures(api_client, org):
    ip = make_asset(org, kind="ip", key="198.51.100.20")
    make_service(ip, 8443)
    exposure = make_exposure(ip, subject="8443/tcp")
    assert api_client.delete(f"{URL}{ip.id}/").status_code == 204
    exposure.refresh_from_db()
    assert (exposure.status, exposure.resolved_at) == ("resolved", TODAY)
    assert _changes(ip.id) == [("archived", "archived_at"), ("exposure_resolved", "unexpected_port")]


def test_changes_newest_first(api_client, org):
    asset = make_asset(org)
    make_change(asset, occurred_at=TODAY - timedelta(days=2))
    make_change(asset, "owner_changed", field="owner_team", old_value="", new_value="sre")
    make_change(make_asset(org), "tagged")
    rows = results(api_client.get(f"{URL}{asset.id}/changes/"))
    assert [(r["kind"], r["occurred_at"]) for r in rows] == [
        ("owner_changed", "2026-11-05T14:30:00Z"), ("created", "2026-11-03T14:30:00Z")]
    assert rows[0]["new_value"] == "sre"


def test_other_orgs_assets_are_not_found(api_client, org, other_org):
    theirs = make_asset(other_org, key="cdn.quillstone-media.example.test")
    assert keys(api_client.get(URL, {"include_archived": "1"})) == []
    for method, path in [("get", ""), ("patch", ""), ("delete", ""), ("get", "changes/")]:
        response = getattr(api_client, method)(f"{URL}{theirs.id}/{path}", {}, format="json")
        assert response.status_code == 404, (method, path)
        assert response.json()["error"]["code"] == "not_found"
    theirs.refresh_from_db()
    assert theirs.archived_at is None
