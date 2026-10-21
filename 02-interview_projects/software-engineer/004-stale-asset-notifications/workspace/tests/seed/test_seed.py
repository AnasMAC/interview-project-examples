import hashlib
import io
import json
import re
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db.models import Count, Max, Min

from atlas.assets.models import Asset, AssetChange, AssetSource
from atlas.assets.ownership import apply_ownership
from atlas.core import clock
from atlas.core.auth import authenticate_key
from atlas.core.management.commands.seed import ANCHOR, PROFILES, asset_target
from atlas.core.models import Membership, Org
from atlas.exposure.models import Exposure
from atlas.exposure.service import evaluate_assets
from atlas.notify.models import Webhook

pytestmark = pytest.mark.django_db


def seed(*args):
    call_command("seed", *args, stdout=io.StringIO())


def digest() -> str:
    rows = [
        list(Asset.objects.order_by("id").values_list(
            "id", "org__slug", "kind", "key", "label", "attributes", "owner_team", "first_seen_at",
            "last_seen_at", "archived_at")),
        list(AssetChange.objects.order_by("id").values_list(
            "id", "asset_id", "kind", "field", "old_value", "new_value", "job_id", "occurred_at")),
        list(Exposure.objects.order_by("id").values_list("id", "asset_id", "rule", "subject", "status")),
        list(AssetSource.objects.order_by("id").values_list("asset_id", "source_name", "last_seen_at")),
    ]
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


def test_seed_loads_the_demo_orgs_with_eight_weeks_of_history():
    out = io.StringIO()
    call_command("seed", stdout=out)
    # The shortcut gets almost every owner and exposure right; the real rules fix the rest.
    fixes = [int(n) for n in re.findall(r"(\d+) rule_fixes", out.getvalue())]
    assert len(fixes) == 3 and sum(fixes) <= 10

    per_org = dict(Asset.objects.values_list("org__slug").annotate(n=Count("id")))
    assert 4_800 <= sum(per_org.values()) <= 5_500
    assert per_org["quillstone-media"] > per_org["harborview-bank"] > per_org["orchid-grid"]
    for slug, profile in PROFILES.items():
        org = Org.objects.get(slug=slug)
        assert (org.timezone, org.allowed_ports) == (profile.timezone, profile.allowed_ports)
        assert authenticate_key(profile.api_key).org == org
        hook = Webhook.objects.get(org=org)
        assert (hook.url, hook.secret) == (f"http://mockhook:9000/hooks/{slug}", profile.webhook_secret)
        assert set(Asset.objects.for_org(org).values_list("kind", flat=True)) == set(Asset.Kind.values)
    window = AssetChange.objects.aggregate(first=Min("occurred_at"), last=Max("occurred_at"))
    assert ANCHOR - timedelta(days=56) <= window["first"] < ANCHOR - timedelta(days=55)
    assert ANCHOR - timedelta(hours=12) < window["last"] <= ANCHOR
    assert Asset.objects.filter(first_seen_at__gt=ANCHOR).count() == 0
    open_rules = set(Exposure.objects.filter(status="open").values_list("rule", flat=True))
    assert open_rules == set(Exposure.Rule.values)

    with clock.frozen(ANCHOR):  # what the real rules would change now: nothing
        for org in Org.objects.all():
            assert apply_ownership(org) == []
            evaluation = evaluate_assets(org)
            assert evaluation.opened == evaluation.resolved == []

    with pytest.raises(CommandError, match="--reset"):
        seed()


def test_harborview_has_nimbus_duplicates_after_the_account_migration():
    seed()

    resources = Asset.objects.filter(org__slug="harborview-bank", kind="cloud_resource")
    old = {key.rsplit(":", 1)[1] for key in resources.filter(key__startswith="nimbus:4471-2210-0093:")
           .values_list("key", flat=True)}
    new = resources.filter(key__startswith="nimbus:acct-7f3k9q2mwd:")
    twins = [a for a in new if a.key.rsplit(":", 1)[1] in old]
    assert twins and all(a.first_seen_at.date().isoformat() >= "2026-10-19" for a in twins)
    assert not resources.filter(key__startswith="nimbus:4471", last_seen_at__date__gt="2026-10-19").exists()


def test_same_seed_gives_the_same_rows_and_reset_keeps_dashboard_users():
    seed("--seed", "7")
    call_command("create_demo_user", stdout=io.StringIO())
    first = digest()

    seed("--seed", "7", "--reset")
    call_command("create_demo_user", stdout=io.StringIO())

    assert digest() == first
    demo = get_user_model().objects.get(username="demo")
    assert demo.check_password("DEMO-atlas-demo")
    assert Membership.objects.filter(user=demo).count() == 3


def test_scale_multiplies_volume_with_quillstone_growing_fastest():
    assert 38_000 <= asset_target("quillstone-media", 8) <= 42_000
    assert asset_target("harborview-bank", 8) == 8 * asset_target("harborview-bank", 1)
    with pytest.raises(CommandError):
        seed("--scale", "0")
