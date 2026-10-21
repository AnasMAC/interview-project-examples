import json
from datetime import UTC, datetime

import pytest

from atlas.importers import nimbus
from atlas.importers.base import ImportFormatError, ObservedLink
from tests.importers.helpers import by_value, fixture_text

V1 = "nimbus/harborview-bank-2026-09-30.v1.json"
V2 = "nimbus/harborview-bank-2026-10-28.v2.json"


def test_v1_export():
    batch = nimbus.parse(fixture_text(V1))
    web = by_value(batch)["nimbus:4471-2210-0093:i-0a91c3e5"]

    assert batch.source_kind == "nimbus"
    assert batch.source_name == "nimbus account 4471-2210-0093"
    assert batch.observed_at == datetime(2026, 9, 30, 4, 0, tzinfo=UTC)
    assert len(batch.observations) == 5
    assert web.kind == "cloud_resource"
    assert web.label == "hvb-online-web-01"
    assert web.external_id == "4471-2210-0093/i-0a91c3e5"
    assert web.attributes == {
        "provider": "nimbus",
        "account_id": "4471-2210-0093",
        "resource_type": "compute.instance",
        "region": "ca-central-2",
        "public_ip": "198.51.100.20",
    }
    assert web.links == (
        ObservedLink("attached", "ip", "198.51.100.20"),
        ObservedLink("attached", "host", "online.harborview-bank.example.test"),
    )


def test_v2_export_maps_renamed_fields_to_the_same_shape():
    v1 = by_value(nimbus.parse(fixture_text(V1)))["nimbus:4471-2210-0093:lb-5d2e7710"]
    batch = nimbus.parse(fixture_text(V2))
    v2 = by_value(batch)["nimbus:acct-7f3k9q2mwd:lb-5d2e7710"]

    assert batch.source_name == "nimbus account acct-7f3k9q2mwd"
    assert v2.label == v1.label
    assert v2.links == v1.links
    assert v2.attributes == v1.attributes | {"account_id": "acct-7f3k9q2mwd"}


def test_account_migration_keeps_resource_ids_but_changes_keys():
    """The v2 account id is new, so every key changes (the Harborview duplicates ticket)."""
    v1 = nimbus.parse(fixture_text(V1))
    v2 = nimbus.parse(fixture_text(V2))

    def resource_ids(batch):
        return {o.value.rsplit(":", 1)[1] for o in batch.observations}

    assert resource_ids(v1) - {"i-0c17aa62"} <= resource_ids(v2)
    assert not {o.value for o in v1.observations} & {o.value for o in v2.observations}


def test_terminated_resources_and_private_addresses_are_left_out():
    batch = nimbus.parse(fixture_text(V2))
    found = by_value(batch)

    assert "nimbus:acct-7f3k9q2mwd:i-0c17aa62" not in found
    assert batch.warnings == ["resource i-0c17aa62: TERMINATED, skipped"]
    reports = found["nimbus:acct-7f3k9q2mwd:i-0d3390fe"]
    assert [link.value for link in reports.links] == ["198.51.100.23", "reports.harborview-bank.example.test"]
    bucket = found["nimbus:acct-7f3k9q2mwd:bkt-hvb-statements"]
    assert bucket.attributes["public_ip"] is None


def test_v2_ipv6_is_normalized_and_keys_are_lower_case():
    text = json.dumps({
        "schema": "nimbus.inventory/v2",
        "generatedAt": "2026-11-03T18:30:00Z",
        "account": {"id": "ACCT-2M8X4C1PZQ"},
        "items": [
            {"resourceId": "I-07E1B2C9", "addresses": [{"ip": "2001:0DB8:06f1::0070", "scope": "public"}]},
            {"resourceId": "i-1", "addresses": [{"ip": "not-an-ip", "scope": "public"}]},
            {"displayName": "no id"},
        ],
    })
    batch = nimbus.parse(text)

    first = batch.observations[0]
    assert first.value == "nimbus:acct-2m8x4c1pzq:i-07e1b2c9"
    assert first.external_id == "ACCT-2M8X4C1PZQ/I-07E1B2C9"
    assert first.label == "I-07E1B2C9"
    assert first.attributes["public_ip"] == "2001:db8:6f1::70"
    assert batch.observations[1].links == ()
    assert batch.warnings == [
        "resource i-1: invalid IP address: 'not-an-ip'",
        "resource #2: no resource id, skipped",
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "invalid JSON"),
        ('{"version": 1, "resources": []}', "no account object"),
        ('{"version": 3, "account": {"number": "1"}, "resources": []}', "unsupported Nimbus export"),
        ('{"version": 1, "account": {"id": "acct-x"}, "resources": []}', "without account.number"),
        ('{"version": 1, "account": {"number": "1"}, "exported_at": "2026-09-30"}', "'resources' list"),
        ('{"version": 1, "account": {"number": "1"}, "resources": []}', "export time"),
    ],
)
def test_unusable_exports_raise(text, message):
    with pytest.raises(ImportFormatError, match=message):
        nimbus.parse(text)
