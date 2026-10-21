import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from atlas.assets.models import Asset, AssetLink, AssetService
from atlas.exposure.models import Exposure
from tests.factories import make_asset, make_exposure, make_link, make_saved_view, make_service

pytestmark = pytest.mark.django_db


def test_migrations_match_models():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)


def test_for_org_scopes_assets_and_their_children(org, other_org):
    host = make_asset(org, key="www.harborview-bank.example.test")
    ip = make_asset(org, kind=Asset.Kind.IP, key="203.0.113.10")
    theirs = make_asset(other_org, kind=Asset.Kind.IP, key="203.0.113.10")
    make_link(host, ip)
    make_service(theirs, port=22)
    assert list(Asset.objects.for_org(org).order_by("id")) == [host, ip]
    assert AssetLink.objects.for_org(other_org).count() == 0
    assert list(AssetService.objects.for_org(other_org)) == list(theirs.services.all())


def test_asset_identity_is_unique_per_org_and_kind(org, other_org):
    make_asset(org, key="api.harborview-bank.example.test")
    make_asset(org, kind=Asset.Kind.DOMAIN, key="api.harborview-bank.example.test")
    make_asset(other_org, key="api.harborview-bank.example.test")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_asset(org, key="api.harborview-bank.example.test")


def test_only_one_open_exposure_per_asset_rule_and_subject(org):
    asset = make_asset(org, kind=Asset.Kind.IP, key="203.0.113.20")
    make_exposure(asset, subject="8443/tcp", status=Exposure.Status.RESOLVED)
    make_exposure(asset, subject="8443/tcp")
    make_exposure(asset, subject="22/tcp")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_exposure(asset, subject="8443/tcp")


def test_shared_saved_view_names_are_unique_per_org(org):
    make_saved_view(org, name="Public IPs")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_saved_view(org, name="Public IPs")
