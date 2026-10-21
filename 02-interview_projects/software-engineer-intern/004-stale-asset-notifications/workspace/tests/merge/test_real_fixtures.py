"""Sanity check against the real importers and sample files (the unit tests
use constructed batches)."""

import pytest
from django.conf import settings

from atlas.assets.models import Asset, AssetChange, AssetLink
from atlas.importers.registry import get_importer
from atlas.merge.service import merge_batch

pytestmark = pytest.mark.django_db

FILES = [
    ("zone_file", "zone/harborview-bank.example.test.zone"),
    ("ct_feed", "ct/harborview-bank-2026-11-04.jsonl"),
    ("port_scan", "scans/harborview-bank-2026-11-04.json"),
]


def _import(org, importer, path):
    text = (settings.ATLAS_IMPORT_ROOT / path).read_text(encoding="utf-8")
    return merge_batch(org, get_importer(importer)(text))


def test_fixtures_merge_into_one_inventory_and_reimport_is_a_no_op(org):
    for importer, path in FILES:
        assert _import(org, importer, path).touched
    counts = (Asset.objects.count(), AssetLink.objects.count(), AssetChange.objects.count())
    www = Asset.objects.get(kind="host", key="www.harborview-bank.example.test")
    # www is named by no explicit CT link: only the wildcard SAN covers it.
    assert www.links_in.filter(relation="covers", asset__label__startswith="*.").exists()

    for importer, path in FILES:
        result = _import(org, importer, path)
        assert result.created == result.updated == [] and result.changes == []
    assert (Asset.objects.count(), AssetLink.objects.count(), AssetChange.objects.count()) == counts


@pytest.mark.parametrize("order", [FILES[:2], FILES[1::-1]], ids=["zone-first", "ct-first"])
def test_apex_san_and_zone_apex_are_one_domain_asset(org, order):
    for importer, path in order:
        _import(org, importer, path)

    [apex] = Asset.objects.filter(org=org, key="harborview-bank.example.test")
    assert apex.kind == "domain"
    assert sorted(apex.sources.values_list("source_kind", flat=True)) == ["ct_feed", "zone_file"]
    wildcard = Asset.objects.get(org=org, kind="certificate", label="*.harborview-bank.example.test")
    assert apex.links_in.filter(relation="covers", asset=wildcard).count() == 1
    upgraded = AssetChange.objects.filter(asset=apex, kind="updated", field="kind")
    expected = [("host", "domain")] if order[0][0] == "ct_feed" else []
    assert [(c.old_value, c.new_value) for c in upgraded] == expected
