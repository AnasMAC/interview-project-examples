"""Tags, exposures, webhooks, saved views, throttling and unknown routes."""

import pytest

from atlas.assets.models import AssetChange, SavedView
from atlas.notify.models import Webhook
from tests.api.helpers import results
from tests.factories import make_asset, make_exposure, make_saved_view, make_tag, make_user, make_webhook

pytestmark = pytest.mark.django_db


def test_tags_create_list_and_conflict(api_client, org, other_org):
    make_tag(other_org, "prod")
    created = api_client.post("/api/v1/tags/", {"name": "Prod", "description": "Production"}, format="json")
    assert created.status_code == 201 and created.json()["name"] == "prod"
    make_asset(org).tags.add(make_tag(org, "edge"))
    assert [(t["name"], t["asset_count"]) for t in api_client.get("/api/v1/tags/").json()] == [
        ("edge", 1), ("prod", 0)]
    duplicate = api_client.post("/api/v1/tags/", {"name": "prod"}, format="json")
    assert duplicate.status_code == 409


def test_tag_delete_records_untagged_and_is_scoped(api_client, org, other_org):
    asset = make_asset(org)
    asset.tags.add(make_tag(org, "legacy"))
    make_tag(other_org, "theirs")
    assert api_client.delete("/api/v1/tags/theirs/").status_code == 404
    assert api_client.delete("/api/v1/tags/legacy/").status_code == 204
    change = AssetChange.objects.get(asset=asset)
    assert (change.kind, change.old_value) == ("untagged", "legacy")


def test_exposures_filter_and_scope(api_client, org, other_org):
    ip = make_asset(org, kind="ip", key="198.51.100.7")
    opened = make_exposure(ip, subject="8443/tcp")
    make_exposure(ip, rule="admin_panel_public", severity="high", status="resolved")
    make_exposure(make_asset(other_org))
    assert [e["id"] for e in results(api_client.get("/api/v1/exposures/", {"status": "open"}))] == [opened.id]
    assert len(results(api_client.get("/api/v1/exposures/", {"asset": ip.id}))) == 2
    high = results(api_client.get("/api/v1/exposures/", {"severity": "high"}))
    assert [e["rule"] for e in high] == ["admin_panel_public"]
    assert api_client.get("/api/v1/exposures/", {"rule": "weak_tls"}).status_code == 400
    assert api_client.post("/api/v1/exposures/", {}, format="json").status_code == 405


def test_webhook_secret_is_generated_once_and_never_returned(api_client, org):
    body = {"name": "soc", "url": "http://mockhook:9000/hooks/harborview-bank",
            "events": ["exposure.opened", "asset.created", "exposure.opened"]}
    response = api_client.post("/api/v1/webhooks/", body, format="json")
    assert response.status_code == 201, response.content
    secret = response.json()["secret"]
    prefix = "DEMO-whsec-harborview-bank-"
    assert secret.startswith(prefix) and len(secret) == len(prefix) + 12
    assert Webhook.objects.get().secret == secret
    assert response.json()["events"] == ["asset.created", "exposure.opened"]
    hook_id = response.json()["id"]
    assert "secret" not in api_client.get(f"/api/v1/webhooks/{hook_id}/").json()
    rotated = api_client.patch(f"/api/v1/webhooks/{hook_id}/", {"secret": "DEMO-whsec-rotated-0001"},
                               format="json")
    assert rotated.status_code == 200 and "secret" not in rotated.json()
    own = api_client.post("/api/v1/webhooks/", {**body, "secret": "DEMO-whsec-mine-123456"}, format="json")
    assert "secret" not in own.json()


@pytest.mark.parametrize(("field", "value"), [
    ("url", "http://169.254.169.254/latest/meta-data"),
    ("url", "file:///etc/passwd"),
    ("events", ["asset.deleted"]),
    ("events", []),
])
def test_webhook_validation(api_client, org, field, value):
    body = {"name": "x", "url": "https://hooks.harborview-bank.example.test/atlas",
            "events": ["asset.created"]}
    response = api_client.post("/api/v1/webhooks/", {**body, field: value}, format="json")
    assert response.status_code == 400 and field in response.json()["error"]["details"]


def test_other_orgs_webhooks_are_hidden(api_client, other_org):
    theirs = make_webhook(other_org)
    assert api_client.get("/api/v1/webhooks/").json() == []
    response = api_client.patch(f"/api/v1/webhooks/{theirs.id}/", {"enabled": False}, format="json")
    assert response.status_code == 404


def test_saved_views_are_canonical_shared_and_unique(api_client, org):
    make_saved_view(org, name="mine", owner=make_user(orgs=[org]))
    response = api_client.post("/api/v1/saved-views/", {"name": "Hot hosts",
                               "querystring": "?tag=prod&kind=host&cursor=x&exposure=any"}, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["querystring"] == "exposure=any&kind=host&tag=prod"
    assert [v["name"] for v in api_client.get("/api/v1/saved-views/").json()] == ["Hot hosts"]
    again = api_client.post("/api/v1/saved-views/", {"name": "Hot hosts", "querystring": ""}, format="json")
    assert again.status_code == 409
    bad = api_client.post("/api/v1/saved-views/", {"name": "x", "querystring": "kind=vm"}, format="json")
    assert bad.status_code == 400 and "querystring" in bad.json()["error"]["details"]
    personal = SavedView.objects.get(name="mine")
    assert api_client.delete(f"/api/v1/saved-views/{personal.id}/").status_code == 404


def test_throttle_is_per_api_key(api_client, other_api_client, org, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"api_key": "2/min"}}
    assert [api_client.get("/api/v1/tags/").status_code for _ in range(2)] == [200, 200]
    throttled = api_client.get("/api/v1/assets/")
    assert throttled.status_code == 429 and throttled["Retry-After"] == "60"
    assert throttled.json()["error"] == {"code": "throttled", "message": throttled.json()["error"]["message"],
                                         "details": {"retry_after_seconds": 60}}
    assert other_api_client.get("/api/v1/tags/").status_code == 200


def test_unknown_api_path_answers_json_404(api_client):
    response = api_client.get("/api/v1/nope/")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
