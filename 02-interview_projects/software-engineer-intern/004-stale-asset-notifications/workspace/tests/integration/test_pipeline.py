"""End to end, nothing faked: import jobs -> the real worker -> merge, ownership,
exposures -> signed webhooks to an in-process mockhook -> API and dashboard."""

import logging
import threading
import time

import pytest

from atlas.assets.models import Asset, AssetLink, AssetService
from atlas.exposure.models import Exposure
from atlas.jobs.models import Job
from atlas.jobs.queue import enqueue
from atlas.jobs.worker import run_once
from atlas.notify.models import OutboxEvent
from mockhook.server import MockhookServer
from tests.factories import TODAY, make_rule, make_webhook

pytestmark = pytest.mark.django_db
SECRET = "DEMO-whsec-harborview-bank-e33d70005377"
HVB = "harborview-bank.example.test"
IMPORTS = [
    ("zone_file", f"zone/{HVB}.zone"),
    ("ct_feed", "ct/harborview-bank-2026-11-04.jsonl"),
    ("port_scan", "scans/harborview-bank-2026-11-04.json"),
    ("nimbus", "nimbus/harborview-bank-2026-09-30.v1.json"),
]


@pytest.fixture
def mockhook(tmp_path):
    # Its clock follows the frozen test clock, as it follows ATLAS_NOW in compose.
    server = MockhookServer(("127.0.0.1", 0), tmp_path / "deliveries.jsonl", secret=SECRET,
                            clock_offset=TODAY.timestamp() - time.time())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def run_worker_until_idle(limit=20):
    for _ in range(limit):
        if not run_once("pytest-worker"):
            return
    raise AssertionError("worker never went idle")


def test_fixture_imports_flow_through_to_webhooks_api_and_dashboard(org, api_client, dashboard_client,
                                                                     mockhook, caplog):
    caplog.set_level(logging.INFO)  # as in compose: INFO records with all their extra fields get built
    make_rule(org, f"*.{HVB}", "platform-sre", priority=100)
    make_rule(org, "198.51.100.0/24", "network-engineering", pattern_type="cidr", priority=90)
    make_webhook(org, url=f"http://localhost:{mockhook.server_port}/hooks/harborview-bank", secret=SECRET)
    jobs = [enqueue(org, "import.run", {"importer": name, "path": path}) for name, path in IMPORTS]

    run_worker_until_idle()

    assert set(Job.objects.filter(pk__in=[j.pk for j in jobs]).values_list("status", flat=True)) == {"done"}
    assert [r.importer for r in caplog.records if r.msg == "import.completed"] == [n for n, _ in IMPORTS]
    assets = Asset.objects.for_org(org)
    assert list(assets.filter(key=HVB).values_list("kind", flat=True)) == ["domain"]  # one apex
    www = assets.get(kind="host", key=f"www.{HVB}")
    assert www.links_out.get(relation="cname").target.key == f"web-lb.{HVB}"
    assert www.links_in.filter(relation="covers", asset__kind="certificate").exists()  # wildcard SAN
    assert assets.get(kind="host", key=f"web-lb.{HVB}").links_out.filter(relation="resolves_to").count() == 3
    online_ip = AssetService.objects.filter(asset__org=org, asset__key="198.51.100.20", closed_at=None)
    assert sorted(online_ip.values_list("port", flat=True)) == [80, 443]
    assert assets.filter(kind="cloud_resource", key__startswith="nimbus:4471-2210-0093:").exists()
    assert AssetLink.objects.filter(asset__org=org, relation="attached").exists()
    assert assets.get(key=f"vpn.{HVB}").owner_team == "platform-sre"
    assert assets.get(key="198.51.100.20").owner_team == "network-engineering"

    open_rows = Exposure.objects.for_org(org).filter(status="open").select_related("asset")
    assert {(e.asset.label, e.rule, e.subject, e.severity) for e in open_rows} == {
        (f"promo-2025.{HVB}", "dangling_cname", "harborview-promo.landingly.example.test", "high"),
        (f"online.{HVB}", "cert_expiring", "", "medium"),  # 2026-11-14: 9 days left
        (f"vpn.{HVB}", "cert_expiring", "", "critical"),  # expired 2026-10-30
        (f"promo-2025.{HVB}", "cert_expiring", "", "critical"),  # expired 2025-05-30
        ("198.51.100.20", "unexpected_port", "80/tcp", "medium"),
        ("198.51.100.30", "unexpected_port", "500/udp", "medium"),
    }

    outbox = OutboxEvent.objects.for_org(org)
    assert outbox.exists() and set(outbox.values_list("status", flat=True)) == {"delivered"}
    lines = mockhook.tail(1000)
    assert len(lines) == outbox.count() and all(line["signature_ok"] for line in lines)
    events = {line["event"] for line in lines}
    assert {"asset.created", "exposure.opened", "import.completed"} <= events

    body = api_client.get("/api/v1/assets/", {"exposure": "cert_expiring", "kind": "certificate"}).json()
    labels = sorted(asset["label"] for asset in body["results"])
    assert labels == [f"{name}.{HVB}" for name in ("online", "promo-2025", "vpn")]
    page = dashboard_client.get("/assets/", {"exposure": "dangling_cname"})
    assert page.status_code == 200 and [a.key for a in page.context["assets"]] == [f"promo-2025.{HVB}"]
