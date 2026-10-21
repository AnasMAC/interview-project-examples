from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from gatekeeper.core.tables import audit_events, waivers
from gatekeeper.waivers.expiry import expire_due
from tests.factories import TODAY, auth_header


@pytest.fixture
def keys(factory):
    team = factory.team("payments-api")
    factory.service(team, "payments-api")
    return {"team": auth_header(factory.team_key(team)),
            "other": auth_header(factory.team_key(factory.team("ledger-core"))),
            "reviewer": auth_header(factory.reviewer_key())}


def _request(client, keys, **body):
    body = {"service": "payments-api", "rule": "sast.max_high", "version_range": ">=4.12,<4.13",
            "reason": "fix lands in 4.13 (PAY-2211)",
            "expires_at": (TODAY + timedelta(days=14)).isoformat(), **body}
    return client.post("/v1/waivers", json=body, headers=keys["team"])


def _actions(conn):
    return conn.execute(select(audit_events.c.action, audit_events.c.actor)
                        .order_by(audit_events.c.id)).all()


def test_request_review_and_revoke(client, conn, keys):
    created = _request(client, keys)
    assert created.status_code == 201
    waiver = created.json
    assert (waiver["status"], waiver["rule"], waiver["team"]) == (
        "pending", "sast.new_high_max", "payments-api")
    url = f"/v1/waivers/{waiver['id']}"

    denied = client.post(url + "/approve", headers=keys["team"])
    assert (denied.status_code, denied.json["error"]["code"]) == (403, "role_required")
    approved = client.post(url + "/approve", json={"note": "ok until 4.13"},
                           headers=keys["reviewer"])
    assert approved.json["status"] == "approved"
    assert approved.json["reviewed_by"] == "key:security-review"
    again = client.post(url + "/reject", json={"note": "no"}, headers=keys["reviewer"])
    assert (again.status_code, again.json["error"]["code"]) == (409, "invalid_transition")

    assert client.post(url + "/revoke", headers=keys["other"]).status_code == 404
    assert client.get(url, headers=keys["other"]).status_code == 404
    assert client.post(url + "/revoke", headers=keys["team"]).json["status"] == "revoked"
    assert _actions(conn) == [("waiver.requested", "key:payments-api-ci"),
                              ("waiver.approved", "key:security-review"),
                              ("waiver.revoked", "key:payments-api-ci")]


@pytest.mark.parametrize(("body", "code"), [
    ({"expires_at": (TODAY + timedelta(days=90, seconds=1)).isoformat()}, "waiver_too_long"),
    ({"expires_at": (TODAY - timedelta(minutes=1)).isoformat()}, "validation_failed"),
    ({"expires_at": "2026-12-20T00:00:00"}, "validation_failed"),
    ({"version_range": "~4.12"}, "validation_failed"),
    ({"service": "refunds-worker"}, "unknown_service"),
])
def test_invalid_requests_are_422(client, keys, body, code):
    response = _request(client, keys, **body)

    assert (response.status_code, response.json["error"]["code"]) == (422, code)


def test_reject_needs_a_note_and_lists_are_scoped(client, factory, keys):
    waiver_id = _request(client, keys).json["id"]
    factory.waiver(team=factory.team("card-issuing"))

    response = client.post(f"/v1/waivers/{waiver_id}/reject", json={}, headers=keys["reviewer"])
    assert response.status_code == 422
    listed = client.get("/v1/waivers?status=pending", headers=keys["team"]).json
    assert [w["id"] for w in listed["data"]] == [waiver_id] and listed["meta"]["total"] == 1
    assert client.get("/v1/waivers", headers=keys["reviewer"]).json["meta"]["total"] == 2
    assert client.get("/v1/waivers?team=card-issuing", headers=keys["team"]).status_code == 404


def test_expiry_is_at_the_exact_instant_and_audited(conn, factory):
    due = factory.waiver(expires_at=TODAY + timedelta(seconds=1))
    pending = factory.waiver(status="pending", expires_at=TODAY - timedelta(hours=3))
    factory.waiver(status="rejected", expires_at=TODAY - timedelta(days=1))
    later = factory.waiver(expires_at=TODAY + timedelta(hours=2))

    assert expire_due(conn, at=TODAY) == [pending.id]
    assert expire_due(conn, at=TODAY + timedelta(seconds=1)) == [due.id]
    assert expire_due(conn, at=TODAY + timedelta(hours=1, minutes=59)) == []
    statuses = dict(conn.execute(select(waivers.c.id, waivers.c.status)).all())
    assert statuses[due.id] == "expired" and statuses[later.id] == "approved"
    assert [a for a, _ in _actions(conn)] == ["waiver.expired", "waiver.expired"]
