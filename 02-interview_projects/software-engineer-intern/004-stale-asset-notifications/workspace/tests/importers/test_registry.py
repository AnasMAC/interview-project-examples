import pytest

from atlas.importers import ct_feed, nimbus, port_scan, zone_file
from atlas.importers.registry import UnknownImporter, get_importer
from tests.importers.helpers import fixture_text


def test_registry_names_match_source_kinds():
    assert get_importer("zone_file") is zone_file.parse
    assert get_importer("nimbus") is nimbus.parse
    assert get_importer("ct_feed") is ct_feed.parse
    assert get_importer("port_scan") is port_scan.parse
    batch = get_importer("nimbus")(fixture_text("nimbus/orchid-grid-2026-11-03.v2.json"))
    assert batch.importer == batch.source_kind == "nimbus"


def test_unknown_importer():
    with pytest.raises(UnknownImporter, match="known: ct_feed, nimbus, port_scan, zone_file"):
        get_importer("csv")
