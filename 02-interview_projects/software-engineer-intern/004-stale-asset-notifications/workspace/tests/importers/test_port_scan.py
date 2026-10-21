import json
from datetime import UTC, datetime

import pytest

from atlas.importers import port_scan
from atlas.importers.base import ImportFormatError, ObservedLink, ObservedService
from tests.factories import TODAY
from tests.importers.helpers import by_value, fixture_text


def test_orchid_scan_open_ports_only_with_service_mapping():
    batch = port_scan.parse(fixture_text("scans/orchid-grid-2026-11-04.json"))
    found = by_value(batch)

    assert batch.source_kind == "port_scan"
    assert batch.source_name == "periscope external-daily"
    assert batch.observed_at == datetime(2026, 11, 4, 9, 12, 18, tzinfo=UTC)
    assert batch.warnings == []
    gateway = found["203.0.113.77"]
    assert gateway.kind == "ip"
    assert gateway.attributes == {"version": 4}
    assert [(s.port, s.protocol, s.service) for s in gateway.services] == [
        (22, "tcp", "ssh"),
        (8443, "tcp", "https"),
        (161, "udp", "snmp"),
    ]
    admin = gateway.services[1]
    assert admin.product == "Gridline admin console 3.7"
    assert admin.banner.endswith("<title>Gridline Substation Gateway - Admin Login</title>")
    assert "\r" not in admin.banner
    # no service name: well-known name for the port; down host left out
    assert found["203.0.113.68"].services == (ObservedService(443, "tcp", "https"),)
    assert "203.0.113.79" not in found
    assert found["2001:db8:6f1::77"].attributes == {"version": 6}


def test_target_hostnames_become_hosts_ptr_names_do_not():
    found = by_value(port_scan.parse(fixture_text("scans/orchid-grid-2026-11-04.json")))

    assert found["gw.orchid-grid.example.test"].links == (
        ObservedLink("resolves_to", "ip", "203.0.113.77"),
        ObservedLink("resolves_to", "ip", "2001:db8:6f1::77"),
    )
    assert "static-77.akl.transitnet.example.test" not in found


def test_later_scan_no_longer_reports_ssh():
    old = by_value(port_scan.parse(fixture_text("scans/harborview-bank-2026-10-22.json")))
    new = by_value(port_scan.parse(fixture_text("scans/harborview-bank-2026-11-04.json")))

    def ports(observation):
        return {(s.port, s.protocol) for s in observation.services}

    assert ports(old["198.51.100.30"]) == {(443, "tcp"), (22, "tcp"), (500, "udp")}
    assert ports(new["198.51.100.30"]) == {(443, "tcp"), (500, "udp")}
    assert "2001:db8:4b0::10" in new


def test_up_host_without_open_ports_is_still_reported():
    closed = {"port": 443, "protocol": "tcp", "state": "closed"}
    host = {"address": "192.0.2.5", "state": "up", "ports": [closed]}
    text = json.dumps({"scan": {"finished_at": "2026-11-04T08:00:00Z"}, "hosts": [host]})
    batch = port_scan.parse(text)

    assert batch.observations[0].services == ()
    assert batch.source_name == "periscope"


def test_bad_entries_are_skipped_with_warnings_and_long_fields_truncated():
    text = json.dumps({"hosts": [
        {"address": "192.0.2.5", "ports": [
            {"port": 70000, "state": "open"},
            {"port": 132, "protocol": "sctp", "state": "open"},
            {"port": 443, "state": "open", "service": {"banner": "x" * 600}},
            {"port": 443, "state": "open", "service": {"name": "duplicate"}},
        ]},
        {"address": "fe80::1%eth0"},
        "garbage",
    ]})
    batch = port_scan.parse(text)

    assert batch.observed_at == TODAY
    (observation,) = batch.observations
    assert len(observation.services) == 1
    assert len(observation.services[0].banner) == 512
    assert [w.split(":")[0] for w in batch.warnings] == [
        "scan has no readable finished_at; using the import time",
        "192.0.2.5",
        "192.0.2.5",
        "host #1",
        "host #2",
    ]


@pytest.mark.parametrize("text", ["", "[]", '{"scanner": {"name": "periscope"}}'])
def test_unusable_results_raise(text):
    with pytest.raises(ImportFormatError):
        port_scan.parse(text)
