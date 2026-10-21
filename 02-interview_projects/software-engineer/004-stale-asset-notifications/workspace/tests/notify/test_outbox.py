import pytest

from atlas.assets.models import Asset
from atlas.exposure.service import evaluate_assets
from atlas.notify.models import OutboxEvent
from atlas.notify.outbox import enqueue, publish_changes
from tests.factories import make_asset, make_change, make_service, make_webhook

pytestmark = pytest.mark.django_db


def test_enqueue_targets_enabled_subscribed_hooks_of_the_org(org, other_org):
    wanted = make_webhook(org)
    make_webhook(org, enabled=False)
    make_webhook(org, events=["exposure.opened"])
    make_webhook(other_org)
    [row] = enqueue(org, "import.completed", {"job_id": 7})
    assert (row.webhook, row.org, row.payload, row.status) == (wanted, org, {"job_id": 7}, "pending")
    assert OutboxEvent.objects.count() == 1
    with pytest.raises(ValueError, match="unknown webhook event"):
        enqueue(org, "asset.deleted", {})


def test_publish_changes_groups_by_asset(org):
    make_webhook(org)
    make_webhook(org, events=["exposure.opened"])
    new_ip = make_asset(org, Asset.Kind.IP, key="198.51.100.30", owner_team="netops")
    make_service(new_ip, 9200, product="Kibana")
    host = make_asset(org)
    changes = [
        make_change(new_ip),
        make_change(host, "updated", field="label", old_value="a", new_value="b"),
        make_change(new_ip, "service_opened", field="9200/tcp"),
        *evaluate_assets(org, [new_ip.id]).changes,
    ]
    rows = publish_changes(org, changes)
    assert [r.event for r in rows] == [
        "asset.created", "exposure.opened", "exposure.opened", "exposure.opened", "exposure.opened",
        "asset.changed",
    ]
    created = rows[0].payload
    assert created["asset"] == {"id": new_ip.id, "kind": "ip", "key": "198.51.100.30",
                                "label": "198.51.100.30", "owner_team": "netops"}
    assert [c["kind"] for c in created["changes"]] == ["created", "service_opened"]
    opened = rows[1].payload["exposure"]
    assert set(opened) == {"id", "rule", "subject", "severity", "title", "opened_at", "resolved_at"}
    assert opened["opened_at"] == "2026-11-05T14:30:00Z" and opened["resolved_at"] is None
    assert rows[-1].payload["changes"] == [{"kind": "updated", "field": "label", "old": "a", "new": "b"}]


def test_publish_changes_without_hooks_or_with_foreign_changes(org, other_org):
    asset = make_asset(org)
    assert publish_changes(org, [make_change(asset)]) == []
    make_webhook(org)
    with pytest.raises(ValueError, match="another org"):
        publish_changes(org, [make_change(make_asset(other_org))])
