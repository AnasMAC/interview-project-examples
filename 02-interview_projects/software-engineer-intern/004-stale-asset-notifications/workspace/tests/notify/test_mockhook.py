"""mockhook runs in-process on 127.0.0.1 (loopback only, nothing leaves the container)."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from atlas.core import clock
from atlas.notify import delivery
from atlas.notify.signing import sign
from mockhook.server import MockhookServer
from tests.factories import make_outbox, make_webhook

SECRET = "DEMO-whsec-harborview-bank-e33d70005377"


@pytest.fixture
def mockhook(tmp_path):
    server = MockhookServer(("127.0.0.1", 0), tmp_path / "hooks" / "deliveries.jsonl", secret=SECRET)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def call(server, path: str, body: bytes | None = None, signature: str = ""):
    """``(status, parsed JSON)`` from the loopback server; a body makes it a POST."""
    headers = {"X-Atlas-Event": "asset.created", "X-Atlas-Delivery": "41", "X-Atlas-Signature": signature}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", body, headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 (loopback test server)
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_logs_deliveries_and_checks_signatures(mockhook):
    body, now = b'{"event":"asset.created"}', int(time.time())
    hook = "/hooks/harborview-bank"
    assert call(mockhook, hook, body, sign(SECRET, body, now)) == (200, {"ok": True})
    assert call(mockhook, hook, body, sign("wrong-secret", body, now))[0] == 401
    assert call(mockhook, hook, body, sign(SECRET, body, now - 301))[0] == 401
    status, lines = call(mockhook, "/hooks")
    assert status == 200 and [line["signature_ok"] for line in lines] == [True, False, False]
    first = lines[0]
    assert (first["path"], first["delivery"], first["body"]) == (hook, "41", {"event": "asset.created"})


@pytest.mark.django_db
def test_atlas_delivery_is_accepted_by_mockhook(org, mockhook):
    clock.unfreeze()  # mockhook checks the timestamp against the real time
    url = f"http://localhost:{mockhook.server_port}/hooks/harborview-bank"
    hook = make_webhook(org, url=url, secret=SECRET)
    row = make_outbox(hook, "asset.changed", {"asset": {"id": 3}})
    assert delivery.deliver_due() == 1
    row.refresh_from_db()
    assert row.status == "delivered"
    [line] = mockhook.tail()
    assert line["signature_ok"] is True and line["body"]["data"] == {"asset": {"id": 3}}
