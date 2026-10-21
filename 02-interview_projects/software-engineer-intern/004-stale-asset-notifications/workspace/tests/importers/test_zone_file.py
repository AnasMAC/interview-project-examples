import pytest

from atlas.importers import zone_file
from atlas.importers.base import ImportFormatError, ObservedLink
from tests.factories import TODAY
from tests.importers.helpers import by_value, fixture_text

HVB = "harborview-bank.example.test"


def test_harborview_zone_hosts_links_and_apex():
    batch = zone_file.parse(fixture_text(f"zone/{HVB}.zone"))
    found = by_value(batch)

    assert batch.source_kind == "zone_file"
    assert batch.source_name == f"{HVB} zone"
    assert batch.observed_at == TODAY
    assert batch.warnings == []
    assert batch.observations[0].kind == "domain"
    assert batch.observations[0].value == HVB
    assert found[HVB].links == (ObservedLink("resolves_to", "ip", "198.51.100.10"),)
    # blank owner lines inherit "web-lb"; AAAA is compressed by normalize_ip
    assert found[f"web-lb.{HVB}"].links == (
        ObservedLink("resolves_to", "ip", "198.51.100.10"),
        ObservedLink("resolves_to", "ip", "198.51.100.11"),
        ObservedLink("resolves_to", "ip", "2001:db8:4b0::10"),
    )
    assert found[f"www.{HVB}"].links == (ObservedLink("cname", "host", f"web-lb.{HVB}"),)
    assert found[f"mx2.{HVB}"].links == (ObservedLink("resolves_to", "ip", "203.0.113.25"),)
    assert found[f"www.{HVB}"].attributes == {"zone": HVB}
    assert found[f"www.{HVB}"].kind == "host"


def test_dangling_cname_target_is_a_link_not_an_observation():
    found = by_value(zone_file.parse(fixture_text(f"zone/{HVB}.zone")))

    target = "harborview-promo.landingly.example.test"
    assert found[f"promo-2025.{HVB}"].links == (ObservedLink("cname", "host", target),)
    assert target not in found
    assert f"_dmarc.{HVB}" not in found  # TXT only


def test_older_snapshot_differs_from_latest():
    old = by_value(zone_file.parse(fixture_text(f"zone/{HVB}.2026-10-01.zone")))
    new = by_value(zone_file.parse(fixture_text(f"zone/{HVB}.zone")))

    assert old[f"api.{HVB}"].links[0].value == "198.51.100.22"
    assert new[f"api.{HVB}"].links[0].value == "198.51.100.21"
    assert f"beta-online.{HVB}" in old and f"beta-online.{HVB}" not in new
    assert f"reports.{HVB}" in new


def test_quillstone_zone_quirks():
    batch = zone_file.parse(fixture_text("zone/quillstone-media.example.test.zone"))
    found = by_value(batch)
    qsm = "quillstone-media.example.test"

    # class before TTL, null MX, TXT with ";" inside quotes, TTL with units
    assert found[qsm].links == (ObservedLink("resolves_to", "ip", "203.0.113.140"),)
    assert f"_acme-challenge.www.{qsm}" not in found
    assert f"xn--caf-dma.{qsm}" in found
    # relative $ORIGIN: "@" and names below it move to shop.<zone>
    assert found[f"shop.{qsm}"].kind == "host"
    assert found[f"checkout.shop.{qsm}"].links == (ObservedLink("resolves_to", "ip", "203.0.113.181"),)
    assert found[f"static.shop.{qsm}"].links == (ObservedLink("cname", "host", f"cdn-edge.{qsm}"),)
    assert found[f"checkout.shop.{qsm}"].attributes == {"zone": qsm}
    assert "mx.mailrelay.example.test" not in found  # out-of-zone MX exchange
    assert [w.split(": ", 1)[1] for w in batch.warnings] == [
        f"wildcard record *.preview.{qsm} is not an inventory host, skipped",
        f"legal-archive.example.test is outside the zone {qsm}, skipped",
        "$INCLUDE is not supported, skipped",
    ]


def test_single_line_soa_and_relative_soa_names():
    found = by_value(zone_file.parse(fixture_text("zone/orchid-grid.example.test.zone")))

    assert found["orchid-grid.example.test"].kind == "domain"
    assert found["telemetry.orchid-grid.example.test"].links == (
        ObservedLink("cname", "host", "gw.orchid-grid.example.test"),
    )
    assert found["mail.orchid-grid.example.test"].links  # MX exchange with its own A record


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ("www IN A 2001:db8::1", "A record with address '2001:db8::1'"),
        ("www IN A 999.1.1.1", "invalid IP address"),
        ("www IN LOC 52 22 23 N", "unsupported record type LOC"),
        ("bad..name IN A 192.0.2.1", "invalid hostname label"),
        ("www IN CNAME", "CNAME record without data"),
    ],
)
def test_bad_records_are_skipped_with_a_warning(record, message):
    text = f"$ORIGIN z.example.test.\n@ IN SOA ns hostmaster (1 2 3 4 5)\n{record}\nok IN A 192.0.2.9\n"
    batch = zone_file.parse(text)

    assert len(batch.warnings) == 1
    assert batch.warnings[0].startswith("line 3: ")
    assert message in batch.warnings[0]
    assert "ok.z.example.test" in by_value(batch)


def test_inherited_owner_after_a_bad_owner_is_skipped_too():
    text = "$ORIGIN z.example.test.\n@ SOA ns h (1 2 3 4 5)\n-bad A 192.0.2.1\n  A 192.0.2.2\n"
    batch = zone_file.parse(text)

    assert len(batch.warnings) == 2
    assert [o.value for o in batch.observations] == ["z.example.test"]


def test_relative_name_without_origin_is_a_warning():
    batch = zone_file.parse("a.example.test. IN A 192.0.2.1\nrel IN A 192.0.2.2\n")

    assert [o.value for o in batch.observations] == ["a.example.test"]
    assert "without $ORIGIN" in batch.warnings[0]
    assert batch.source_name == "zone file"


@pytest.mark.parametrize(
    "text",
    ["", '{"format": "nimbus.inventory", "version": 1}', "$ORIGIN z.example.test.\n@ SOA ns h (1 2 3\n"],
)
def test_unusable_files_raise(text):
    with pytest.raises(ImportFormatError):
        zone_file.parse(text)

