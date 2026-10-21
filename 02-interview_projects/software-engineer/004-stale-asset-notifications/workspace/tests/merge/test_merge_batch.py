from datetime import timedelta

import pytest

from atlas.assets.models import Asset, AssetChange, AssetLink, AssetService, AssetSource
from atlas.importers.base import ImportBatch, Observation, ObservedLink, ObservedService
from atlas.merge.service import merge_batch
from tests.factories import TODAY, make_asset, make_job, make_service, make_source

pytestmark = pytest.mark.django_db

WWW = "www.harborview-bank.example.test"
API = "api.harborview-bank.example.test"
IP = "198.51.100.7"
CERT = "c0" * 32
ZONE = "harborview-bank.example.test zone"
NIMBUS = "nimbus account 4471-2210-0093"


def batch(*observations, kind="zone_file", name=ZONE, at=TODAY):
    return ImportBatch(importer=kind, source_kind=kind, source_name=name, observed_at=at,
                       observations=list(observations))


def www(*, label=WWW, attributes=None, ip=IP):
    links = (ObservedLink("resolves_to", "ip", ip),) if ip else ()
    attributes = attributes or {"zone": "harborview-bank.example.test"}
    return Observation("host", WWW, label=label, attributes=attributes, links=links)


def scan(ip, *ports, at=TODAY):
    services = tuple(ObservedService(port, service="https" if port == 443 else "") for port in ports)
    observation = Observation("ip", ip, label=ip, services=services)
    return batch(observation, kind="port_scan", name="edge scan", at=at)


def changes(asset, kind=None):
    rows = AssetChange.objects.filter(asset=asset).order_by("id")
    return [(c.kind, c.field, c.old_value, c.new_value) for c in rows if kind in (None, c.kind)]


def test_creates_assets_with_provenance_and_history(org):
    job = make_job(org)
    result = merge_batch(org, batch(www()), job=job)

    host = Asset.objects.get(org=org, kind="host", key=WWW)
    ip = Asset.objects.get(org=org, kind="ip", key=IP)
    assert result.created == [host.id, ip.id] and result.touched == [host.id, ip.id]
    assert (host.label, host.attributes, host.first_seen_at, host.last_seen_at) == (
        WWW, {"zone": "harborview-bank.example.test"}, TODAY, TODAY)
    assert ip.attributes == {"version": 4}
    for asset in (host, ip):
        source = asset.sources.get()
        assert (source.source_kind, source.source_name, source.first_seen_at) == ("zone_file", ZONE, TODAY)
    assert host.links_out.get().target == ip
    assert changes(host) == [
        ("created", "", None, {"key": WWW, "label": WWW, "source_name": ZONE}),
        ("link_added", "resolves_to", None, IP),
    ]
    assert {(c.job_id, c.source_kind) for c in result.changes} == {(job.id, "zone_file")}
    assert len(result.changes) == AssetChange.objects.count() == 3


def test_reimporting_the_same_snapshot_changes_nothing(org, frozen_clock):
    merge_batch(org, batch(www()))
    counts = [model.objects.count() for model in (Asset, AssetSource, AssetLink, AssetChange)]
    frozen_clock.advance(hours=2)

    result = merge_batch(org, batch(www()))

    assert result.created == result.updated == [] and len(result.unchanged) == 2
    assert result.changes == []
    assert [model.objects.count() for model in (Asset, AssetSource, AssetLink, AssetChange)] == counts
    assert Asset.objects.get(key=WWW).updated_at == TODAY


def test_second_source_adds_provenance_and_widens_seen_window(org):
    merge_batch(org, batch(www(ip=None), at=TODAY - timedelta(days=3)))
    nimbus = Observation("host", WWW.upper())
    result = merge_batch(org, batch(nimbus, kind="nimbus", name=NIMBUS))

    host = Asset.objects.get(key=WWW)
    assert result.updated == [host.id]
    assert (host.first_seen_at, host.last_seen_at) == (TODAY - timedelta(days=3), TODAY)
    assert sorted(host.sources.values_list("source_kind", flat=True)) == ["nimbus", "zone_file"]
    assert changes(host, "source_added") == [("source_added", "nimbus", None, NIMBUS)]


def test_most_recent_source_wins_label_and_attributes(org):
    merge_batch(org, batch(www(attributes={"zone": "a", "ttl": 300}), at=TODAY - timedelta(days=1)))
    newer = Observation("host", WWW, label="Public website", attributes={"zone": "b"})
    merge_batch(org, batch(newer, kind="nimbus", name=NIMBUS))

    host = Asset.objects.get(key=WWW)
    assert host.label == "Public website"
    assert host.attributes == {"zone": "b", "ttl": 300}  # merged key by key
    assert changes(host, "updated") == [
        ("updated", "label", WWW, "Public website"),
        ("updated", "attributes", {"zone": "a", "ttl": 300}, {"zone": "b", "ttl": 300}),
    ]


def test_older_snapshot_adds_provenance_but_never_rolls_back(org):
    merge_batch(org, batch(Observation("host", WWW, label="current", attributes={"zone": "new"})))
    old = Observation("host", WWW, label="stale", attributes={"zone": "old"}, external_id="r-1")
    result = merge_batch(org, batch(old, kind="nimbus", name=NIMBUS, at=TODAY - timedelta(days=30)))

    host = Asset.objects.get(key=WWW)
    assert (host.label, host.attributes) == ("current", {"zone": "new"})
    assert (host.first_seen_at, host.last_seen_at) == (TODAY - timedelta(days=30), TODAY)
    assert host.sources.get(source_kind="nimbus").raw == {"zone": "old"}
    assert [c.kind for c in result.changes] == ["source_added"]


def test_source_row_keeps_the_latest_raw_and_seen_window(org):
    asset = make_asset(org, key=WWW, last_seen_at=TODAY - timedelta(days=9))
    source = make_source(asset, source_name=ZONE, raw={"ttl": 60}, external_id="x",
                         first_seen_at=TODAY - timedelta(days=9), last_seen_at=TODAY - timedelta(days=9))
    merge_batch(org, batch(Observation("host", WWW, attributes={"ttl": 300}), at=TODAY - timedelta(days=2)))
    merge_batch(org, batch(Observation("host", WWW, attributes={"ttl": 5}), at=TODAY - timedelta(days=5)))

    source.refresh_from_db()
    assert (source.raw, source.external_id) == ({"ttl": 300}, "x")
    assert source.first_seen_at == TODAY - timedelta(days=9)
    assert source.last_seen_at == TODAY - timedelta(days=2)


def test_link_targets_are_reused_and_links_not_duplicated(org):
    ip = make_asset(org, kind="ip", key=IP, label="edge")
    merge_batch(org, batch(www()))
    merge_batch(org, batch(www(), at=TODAY + timedelta(hours=1)))

    link = AssetLink.objects.get()
    assert (link.target_id, link.first_seen_at) == (ip.id, TODAY)
    assert link.last_seen_at == TODAY + timedelta(hours=1)
    ip.refresh_from_db()
    assert ip.label == "edge" and ip.sources.get().source_name == ZONE
    assert len(changes(ip, "source_added")) == 1


def test_duplicate_observations_in_one_batch_fold_into_one_asset(org):
    second_ip = ObservedLink("resolves_to", "ip", "203.0.113.9")
    result = merge_batch(org, batch(www(), Observation("host", WWW.upper(), links=(second_ip,))))

    host = Asset.objects.get(key=WWW)
    assert Asset.objects.filter(kind="host").count() == 1 and result.created.count(host.id) == 1
    assert sorted(host.links_out.values_list("target__key", flat=True)) == ["198.51.100.7", "203.0.113.9"]


def test_invalid_values_are_skipped_with_a_warning(org):
    bad_link = ObservedLink("resolves_to", "ip", "not-an-ip")
    imported = batch(Observation("host", "bad..name"), Observation("host", WWW, links=(bad_link,)))
    result = merge_batch(org, imported)

    assert [a.key for a in Asset.objects.all()] == [WWW] and len(result.created) == 1
    assert len(imported.warnings) == 2 and "bad..name" in imported.warnings[0]


def test_certificate_covers_matching_hosts_only(org, other_org):
    keys = (WWW, API, "harborview-bank.example.test", "a.b.harborview-bank.example.test", "shop.example.test")
    hosts = {key: make_asset(org, key=key) for key in keys}
    make_asset(other_org, key=API)
    sans = ["*.harborview-bank.example.test", "shop.example.test"]
    certificate = Observation("certificate", CERT, label="*.harborview-bank.example.test",
                              attributes={"sans": sans})
    result = merge_batch(org, batch(certificate, kind="ct_feed", name="ct log"))

    covered = AssetLink.objects.filter(relation="covers").values_list("target_id", flat=True)
    assert sorted(covered) == sorted(hosts[key].id for key in (WWW, API, "shop.example.test"))
    assert len([c for c in result.changes if c.kind == "link_added"]) == 3


def test_certificate_covers_the_apex_domain_once_even_with_importer_links(org):
    apex = make_asset(org, kind="domain", key="harborview-bank.example.test")
    sans = ["harborview-bank.example.test", WWW]
    certificate = Observation("certificate", CERT, attributes={"sans": sans},
                              links=(ObservedLink("covers", "host", WWW),))
    merge_batch(org, batch(certificate, kind="ct_feed", name="ct log"))
    merge_batch(org, batch(certificate, kind="ct_feed", name="ct log"))

    covered = AssetLink.objects.filter(relation="covers").values_list("target__kind", "target__key")
    assert sorted(covered) == [("domain", apex.key), ("host", WWW)]


def test_host_created_later_gets_covered_by_existing_certificate(org):
    sans = {"sans": ["*.harborview-bank.example.test"]}
    certificate = make_asset(org, kind="certificate", key=CERT, attributes=sans)
    make_asset(org, kind="certificate", key="d1" * 32, attributes={"sans": ["other.example.test"]})
    result = merge_batch(org, batch(www(ip=None), Observation("host", "x.y.harborview-bank.example.test")))

    link = AssetLink.objects.get(relation="covers")
    assert (link.asset_id, link.target.key, link.source_kind) == (certificate.id, WWW, "zone_file")
    assert certificate.id in result.updated
    assert changes(certificate, "link_added") == [("link_added", "covers", None, WWW)]


def test_port_scan_opens_closes_and_reopens_services(org, frozen_clock):
    merge_batch(org, scan(IP, 443, 22))
    ip = Asset.objects.get(key=IP)
    assert sorted(ip.services.values_list("port", "service")) == [(22, ""), (443, "https")]

    later = TODAY + timedelta(days=1)
    merge_batch(org, scan(IP, 443, at=later))
    ssh = ip.services.get(port=22)
    assert ssh.closed_at == later and ip.services.get(port=443).closed_at is None

    merge_batch(org, scan(IP, 443, 22, at=later + timedelta(days=1)))
    ssh.refresh_from_db()
    assert ssh.closed_at is None
    assert [(k, f) for k, f, _, _ in changes(ip) if k.startswith("service")] == [
        ("service_opened", "443/tcp"), ("service_opened", "22/tcp"),
        ("service_closed", "22/tcp"), ("service_opened", "22/tcp"),
    ]


def test_older_scan_neither_closes_nor_reopens(org):
    ip = make_asset(org, kind="ip", key=IP)
    seen = make_service(ip, port=8443, last_seen_at=TODAY)
    gone = make_service(ip, port=22, last_seen_at=TODAY - timedelta(days=3),
                        closed_at=TODAY - timedelta(days=1))
    merge_batch(org, scan(IP, 22, at=TODAY - timedelta(days=2)))

    seen.refresh_from_db()
    gone.refresh_from_db()
    assert seen.closed_at is None and gone.closed_at == TODAY - timedelta(days=1)
    assert gone.last_seen_at == TODAY - timedelta(days=2)


def test_only_port_scans_close_services_and_only_of_scanned_assets(org):
    ip, other = make_asset(org, kind="ip", key=IP), make_asset(org, kind="ip", key="198.51.100.8")
    make_service(ip, port=22)
    make_service(other, port=22)
    merge_batch(org, batch(Observation("ip", IP)))
    merge_batch(org, scan("198.51.100.9", 443))
    assert AssetService.objects.filter(closed_at__isnull=False).count() == 0


def test_port_scan_closes_on_up_addresses_but_not_on_named_hosts(org):
    host, ip = make_asset(org, key=WWW), make_asset(org, kind="ip", key=IP)
    make_service(host, port=8080)
    make_service(ip, port=22)
    target = Observation("host", WWW, links=(ObservedLink("resolves_to", "ip", IP),))
    imported = batch(Observation("ip", IP), target, kind="port_scan", name="edge scan")
    merge_batch(org, imported)

    assert host.services.get().closed_at is None
    assert ip.services.get().closed_at == TODAY


def test_archived_asset_seen_again_is_restored(org):
    archived = make_asset(org, key=WWW, archived_at=TODAY - timedelta(days=1),
                          last_seen_at=TODAY - timedelta(days=5))
    result = merge_batch(org, batch(Observation("host", WWW)))

    archived.refresh_from_db()
    assert archived.archived_at is None and result.updated == [archived.id]
    assert changes(archived, "updated") == [("updated", "archived_at", "2026-11-04T14:30:00Z", None)]


def test_snapshot_older_than_the_archive_does_not_restore(org):
    archived = make_asset(org, key=WWW, archived_at=TODAY - timedelta(days=1),
                          last_seen_at=TODAY - timedelta(days=5))
    merge_batch(org, batch(Observation("host", WWW), at=TODAY - timedelta(days=2)))
    archived.refresh_from_db()
    assert archived.archived_at == TODAY - timedelta(days=1)


def test_other_orgs_are_never_touched(org, other_org):
    theirs = make_asset(other_org, key=WWW, label="theirs")
    make_asset(other_org, kind="ip", key=IP)
    result = merge_batch(org, batch(www(label="ours")))

    theirs.refresh_from_db()
    assert theirs.label == "theirs" and not theirs.sources.exists() and not theirs.links_out.exists()
    assert set(result.created) == set(Asset.objects.filter(org=org).values_list("id", flat=True))
    assert Asset.objects.filter(org=other_org).count() == 2
