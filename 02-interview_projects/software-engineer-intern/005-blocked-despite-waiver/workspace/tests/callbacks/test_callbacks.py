from __future__ import annotations

import json
import threading
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from ci_mock.__main__ import make_server
from gatekeeper.callbacks import delivery
from gatekeeper.callbacks.service import enqueue, replay
from gatekeeper.callbacks.signing import sign, verify
from gatekeeper.core.config import get_settings
from gatekeeper.core.tables import audit_events, callback_outbox
from tests.factories import TODAY

NOW = int(TODAY.timestamp())


def test_signature_covers_timestamp_and_exact_body():
    body = b'{"event":"evaluation.decided"}'
    signature = sign("DEMO-whsec-t-0000test0000", NOW, body)

    assert signature.startswith("sha256=") and len(signature) == 71
    assert verify("DEMO-whsec-t-0000test0000", NOW, body, signature, now=NOW + 300)
    assert not verify("DEMO-whsec-t-0000test0000", NOW, body, signature, now=NOW + 301)
    assert not verify("DEMO-whsec-t-0000test0000", NOW + 1, body, signature, now=NOW)
    assert not verify("DEMO-whsec-t-0000test0000", NOW, body + b" ", signature, now=NOW)
    assert not verify("other", NOW, body, signature, now=NOW)


def test_backoff_doubles_up_to_an_hour():
    assert [delivery.backoff_s(n) for n in (1, 2, 3, 7, 8, 20)] == [30, 60, 120, 1920, 3600, 3600]


@pytest.fixture
def sent(monkeypatch):
    calls = []
    status = {"code": 204}

    def fake_post(url, body, headers, timeout_s):
        calls.append((url, body, headers))
        if isinstance(status["code"], Exception):
            raise status["code"]
        return status["code"]

    monkeypatch.setattr(delivery, "post", fake_post)
    return calls, status


def _row(conn, outbox_id):
    return conn.execute(select(callback_outbox).where(callback_outbox.c.id == outbox_id)).one()


def test_due_callback_is_signed_and_delivered(conn, factory, sent):
    team = factory.team("payments-api")
    outbox_id = enqueue(conn, team_id=team.id, event="evaluation.decided",
                        url="http://ci-mock:9100/callbacks/payments-api/payments-api",
                        payload={"event": "evaluation.decided", "evaluation": {"id": 7}})
    factory.outbox(team, next_attempt_at=TODAY + timedelta(seconds=1))  # not due yet

    assert delivery.deliver_due() == 1
    url, body, headers = sent[0][0]
    assert json.loads(body) == {"event": "evaluation.decided", "evaluation": {"id": 7}}
    assert b" " not in body and headers["X-Gatekeeper-Delivery"] == str(outbox_id)
    assert verify(team.callback_secret, int(headers["X-Gatekeeper-Timestamp"]), body,
                  headers["X-Gatekeeper-Signature"], now=NOW)
    row = _row(conn, outbox_id)
    assert (row.status, row.attempts, row.delivered_at) == ("delivered", 1, TODAY)
    assert delivery.deliver_due() == 0


def test_failures_back_off_then_go_dead_with_an_audit_event(conn, factory, sent, monkeypatch):
    monkeypatch.setattr(delivery, "get_settings",
                        lambda: replace(get_settings(), callback_max_attempts=3))
    calls, status = sent
    outbox_id = factory.outbox(factory.team()).id
    status["code"] = 500
    delivery.deliver_due()
    row = _row(conn, outbox_id)
    assert (row.status, row.attempts, row.last_error) == ("pending", 1, "HTTP 500")
    assert row.next_attempt_at == TODAY + timedelta(seconds=30)

    status["code"] = TimeoutError("timed out")
    conn.execute(callback_outbox.update().values(next_attempt_at=TODAY))
    delivery.deliver_due()
    assert _row(conn, outbox_id).next_attempt_at == TODAY + timedelta(seconds=60)
    conn.execute(callback_outbox.update().values(next_attempt_at=TODAY))
    delivery.deliver_due()

    row = _row(conn, outbox_id)
    assert (row.status, row.attempts, row.last_error) == ("dead", 3, "TimeoutError: timed out")
    dead = conn.execute(select(audit_events)).one()
    assert (dead.action, dead.subject_id, dead.details["attempts"]) == (
        "callback.dead", outbox_id, 3)
    assert len(calls) == 3


def test_hosts_outside_the_dev_allow_list_are_never_called(conn, factory, sent):
    outbox_id = factory.outbox(url="https://hooks.attacker.test/x").id

    delivery.deliver_due()

    assert sent[0] == [] and _row(conn, outbox_id).status == "dead"
    assert delivery.url_allowed("https://forgeline.mossbank.example.test/hooks", get_settings())


def test_replay_resets_a_dead_callback(conn, factory):
    outbox_id = factory.outbox(status="dead", attempts=8, last_error="HTTP 503",
                               next_attempt_at=TODAY - timedelta(days=1)).id

    replay(conn, outbox_id=outbox_id, actor="cli:kwame")

    row = _row(conn, outbox_id)
    assert (row.status, row.attempts, row.next_attempt_at, row.last_error) == (
        "pending", 0, TODAY, None)
    event = conn.execute(select(audit_events)).one()
    assert (event.action, event.actor, event.details["attempts"]) == (
        "callback.replayed", "cli:kwame", 8)


def test_ci_mock_receives_and_verifies_over_loopback(conn, factory, tmp_path, frozen_clock):
    frozen_clock.unfreeze()  # ci-mock checks the timestamp against the wall clock
    team = factory.team("payments-api")
    server = make_server(0, tmp_path / "callbacks.jsonl", {"payments-api": team.callback_secret})
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        due = TODAY - timedelta(days=3650)  # the wall clock may be before TODAY
        good = factory.outbox(team, url=f"{base}/callbacks/payments-api/payments-api",
                              next_attempt_at=due).id
        factory.outbox(factory.team("ledger-core"), url=f"{base}/callbacks/payments-api/x",
                       next_attempt_at=due)
        delivery.deliver_due()
    finally:
        server.shutdown()
        server.server_close()

    lines = [json.loads(line) for line in (tmp_path / "callbacks.jsonl").read_text().splitlines()]
    assert sorted(line["signature_valid"] for line in lines) == [False, True]
    assert _row(conn, good).status == "delivered"
