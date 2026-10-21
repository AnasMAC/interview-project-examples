import io
import json
import urllib.error
from datetime import timedelta

import pytest
from django.db import connections

from atlas.notify import delivery
from atlas.notify.delivery import backoff_seconds, deliver_due, host_allowed
from atlas.notify.signing import verify
from tests.factories import TODAY, make_outbox, make_webhook

pytestmark = pytest.mark.django_db


class FakeOpener:
    """Stands in for the urllib opener; ``responses`` are status codes or exceptions."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        outcome = self.responses.pop(0) if self.responses else 200
        if isinstance(outcome, Exception):
            raise outcome
        if outcome >= 300:
            raise urllib.error.HTTPError(request.full_url, outcome, "error", {}, io.BytesIO())
        response = io.BytesIO(b"ok")
        response.status = outcome
        return response


@pytest.fixture
def opener(monkeypatch):
    def install(*responses):
        monkeypatch.setattr(delivery, "_opener", FakeOpener(*responses))
        return delivery._opener
    return install


@pytest.fixture
def hook(org):
    return make_webhook(org, secret="DEMO-whsec-harborview-bank-e33d70005377")


def test_delivers_a_signed_envelope(hook, opener):
    fake = opener(204)
    row = make_outbox(hook, "exposure.opened", {"asset": {"id": 1}})
    assert deliver_due() == 1
    request, timeout = fake.requests[0]
    body = request.data
    assert json.loads(body) == {"id": f"evt_{row.id}", "event": "exposure.opened", "org": "harborview-bank",
                                "occurred_at": "2026-11-05T14:30:00Z", "data": {"asset": {"id": 1}}}
    assert (request.full_url, request.get_method(), timeout) == (hook.url, "POST", 5)
    headers = [request.get_header(h) for h in ("X-atlas-event", "X-atlas-delivery", "Content-type")]
    assert headers == ["exposure.opened", str(row.id), "application/json"]
    assert verify(hook.secret, body, request.get_header("X-atlas-signature"), now=int(TODAY.timestamp()))
    row.refresh_from_db()
    assert (row.status, row.attempts, row.last_status_code, row.delivered_at) == ("delivered", 1, 204, TODAY)


def test_failures_back_off_then_go_dead(hook, opener, frozen_clock, settings):
    settings.ATLAS_WEBHOOK_MAX_ATTEMPTS = 3
    opener(500, urllib.error.URLError("connection refused"), TimeoutError("timed out"))
    row = make_outbox(hook)

    def attempt():
        assert deliver_due() == 1 and deliver_due() == 0  # the failed row is not due again yet
        row.refresh_from_db()
        return row.status, row.attempts, row.last_status_code, row.last_error

    assert attempt() == ("failed", 1, 500, "HTTP 500")
    assert row.next_attempt_at == TODAY + timedelta(seconds=30)
    frozen_clock.advance(seconds=30)
    assert attempt() == ("failed", 2, None, "connection failed: connection refused")
    assert row.next_attempt_at == frozen_clock.now() + timedelta(seconds=60)
    frozen_clock.advance(minutes=1)
    assert attempt() == ("dead", 3, None, "TimeoutError: timed out")


@pytest.mark.parametrize(("url", "enabled", "error"), [
    ("http://169.254.169.254/latest/meta-data/", True, "blocked host"),
    ("http://mockhook:9000/hooks/x", False, "webhook disabled"),
])
def test_blocked_or_disabled_hooks_go_dead_without_a_request(org, opener, url, enabled, error):
    fake = opener()
    row = make_outbox(make_webhook(org, url=url, enabled=enabled))
    assert deliver_due() == 1 and fake.requests == []
    row.refresh_from_db()
    assert (row.status, row.attempts, row.last_error) == ("dead", 0, error)


def test_limit_and_order(hook, opener):
    fake = opener()
    late = make_outbox(hook, next_attempt_at=TODAY - timedelta(minutes=1))
    early = make_outbox(hook, next_attempt_at=TODAY - timedelta(minutes=5))
    make_outbox(hook, status="delivered", next_attempt_at=TODAY - timedelta(hours=1))
    assert deliver_due(limit=1) == 1 and deliver_due() == 1
    assert [r.get_header("X-atlas-delivery") for r, _ in fake.requests] == [str(early.id), str(late.id)]


@pytest.mark.django_db(transaction=True)
def test_rows_locked_by_another_worker_are_skipped(hook, opener):
    fake = opener()
    row = make_outbox(hook)
    other = connections.create_connection("default")
    try:
        other.set_autocommit(False)
        with other.cursor() as cursor:
            cursor.execute("SELECT id FROM notify_outboxevent WHERE id = %s FOR UPDATE", [row.id])
        assert deliver_due() == 0 and fake.requests == []
        other.rollback()
        assert deliver_due() == 1
    finally:
        other.close()


@pytest.mark.parametrize(("attempts", "seconds"), [(1, 30), (2, 60), (7, 1920), (8, 3600), (20, 3600)])
def test_backoff_seconds(attempts, seconds):
    assert backoff_seconds(attempts) == seconds


@pytest.mark.parametrize(("url", "allowed"), [
    ("http://mockhook:9000/hooks/harborview-bank", True),
    ("https://hooks.harborview-bank.example.test/atlas", True),
    ("http://LOCALHOST:8080/x", True),
    ("http://mockhook@evil.test/", False),
    ("http://example.test.evil.test/", False),
    ("ftp://mockhook/x", False),
    ("http://10.0.0.1/", False),
    ("not a url", False),
])
def test_host_allowed(url, allowed, settings):
    assert host_allowed(url) is allowed
    settings.ATLAS_WEBHOOK_ALLOWED_HOSTS = []  # no restriction, but still http(s) only
    assert host_allowed(url) is not url.startswith(("ftp", "not"))
