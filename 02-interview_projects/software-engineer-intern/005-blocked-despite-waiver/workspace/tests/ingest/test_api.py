from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from gatekeeper.core.app import create_app
from gatekeeper.core.config import get_settings
from gatekeeper.core.contracts import Decision, RuleResult
from gatekeeper.core.tables import evaluations, evidence
from gatekeeper.ingest import idempotency
from tests.factories import TODAY, auth_header


@pytest.fixture
def team(factory):
    return factory.team("payments-api")


@pytest.fixture
def service(factory, team):
    return factory.service(team, "payments-api")


@pytest.fixture
def headers(factory, team):
    return auth_header(factory.team_key(team))


def _post(client, payload, headers, key=None):
    if key is not None:
        headers = {**headers, "Idempotency-Key": key}
    return client.post("/v1/evaluations", json=payload, headers=headers)


def _blocked(factory, team, waiver_id=None):
    policy = factory.policy(team)
    results = [
        RuleResult("dependency.max_severity", "block", "ledgerkit 2.4.1: MBSA-2026-0141 is high",
                   {"violations": []}),
        RuleResult("sast.new_high_max", "warn", "waived: 1 new high SAST finding (max 0)",
                   {"new_high": 1, "max": 0}, waiver_id=waiver_id),
        RuleResult("tests.min_pass_rate", "pass", "pass rate 1.00 (min 0.95)"),
    ]
    return Decision("block", results, policy.id, policy.version)


def test_create_stores_decision_evidence_audit_and_callback(
    client, conn, factory, team, service, headers, downstream, forgeline
):
    waiver = factory.waiver(team, rule="sast.new_high_max")
    downstream.decision = _blocked(factory, team, waiver_id=waiver.id)

    response = _post(client, forgeline, headers)

    assert response.status_code == 201
    view = response.json
    assert response.headers["Location"] == f"/v1/evaluations/{view['id']}"
    assert view["team"] == view["service"] == "payments-api"
    assert (view["decision"], view["policy_version"], view["created_at"]) == (
        "block", 1, "2026-12-02T11:00:00+00:00")
    assert view["reasons"] == downstream.decision.reasons
    assert downstream.evaluated[0]["service_id"] == service.id
    kinds = conn.execute(select(evidence.c.kind).where(evidence.c.evaluation_id == view["id"]))
    assert sorted(kinds.scalars()) == ["dependencies", "sast", "secrets", "signing", "tests"]

    decided, applied = downstream.audit
    assert decided == {"action": "evaluation.decided", "actor": "key:payments-api-ci",
                       "subject_type": "evaluation", "subject_id": view["id"],
                       "team_id": team.id,
                       "details": {"decision": "block", "policy_version": 1,
                                   "rules": ["dependency.max_severity", "sast.new_high_max"],
                                   "waiver_ids": [waiver.id]}}
    assert (applied["action"], applied["subject_id"], applied["details"]) == (
        "waiver.applied", waiver.id, {"evaluation_id": view["id"], "rule": "sast.new_high_max"})
    [callback] = downstream.callbacks
    assert callback["url"] == forgeline["callback"]["url"]
    assert callback["payload"] == {"event": "evaluation.decided", "evaluation": view}


def test_legacy_payload_without_callback(client, factory, downstream, legacy):
    kyc = factory.team("kyc-platform")
    factory.service(kyc, "kyc-api")
    del legacy["callback"]

    response = _post(client, legacy, auth_header(factory.team_key(kyc)))

    assert response.status_code == 201
    assert (response.json["source"], response.json["environment"]) == ("legacy", "production")
    assert downstream.callbacks == []
    assert [a["action"] for a in downstream.audit] == ["evaluation.decided"]


def test_reviewers_cannot_submit(client, factory, service, downstream, forgeline):
    response = _post(client, forgeline, auth_header(factory.reviewer_key()))

    assert response.status_code == 403
    assert response.json["error"]["code"] == "role_required"


def test_service_of_another_team_is_unknown(client, factory, headers, downstream, forgeline):
    factory.service(factory.team("ledger-core"), "payments-api")

    response = _post(client, forgeline, headers)

    assert response.status_code == 422
    assert response.json["error"]["code"] == "unknown_service"
    assert downstream.evaluated == []


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [(b"{not json", 400, "invalid_json"), (b"[1, 2]", 400, "invalid_json"),
     (b'{"schema": "forgeline/v3"}', 422, "unknown_payload_format")],
)
def test_bad_bodies(client, headers, downstream, body, status, code):
    response = client.post("/v1/evaluations", data=body, headers=headers)

    assert response.status_code == status
    assert response.json["error"]["code"] == code


def test_body_over_the_limit_is_413(conn, factory, downstream, forgeline):
    small = create_app(dataclasses.replace(get_settings(), max_payload_bytes=512)).test_client()
    body = json.dumps(forgeline).encode()  # about 1.2 kB

    response = small.post("/v1/evaluations", data=body, headers=auth_header(factory.team_key()))

    assert response.status_code == 413
    assert response.json["error"]["code"] == "payload_too_large"


def test_same_key_and_payload_is_a_replay(
    client, conn, factory, service, headers, downstream, forgeline
):
    first = _post(client, forgeline, headers, key="fl-88213:attempt")
    reordered = json.loads(json.dumps(forgeline, sort_keys=True))
    replay = _post(client, reordered, headers, key="fl-88213:attempt")

    assert (first.status_code, replay.status_code) == (201, 200)
    assert replay.headers[idempotency.REPLAY_HEADER] == "true"
    assert replay.json == first.json
    assert len(downstream.audit) == len(downstream.callbacks) == 1
    count = conn.execute(select(evaluations.c.id).where(evaluations.c.service_id == service.id))
    assert len(count.all()) == 1
    other = factory.team("ledger-core")  # keys are per team
    factory.service(other, "payments-api")
    other_headers = auth_header(factory.team_key(other))
    assert _post(client, forgeline, other_headers, key="fl-88213:attempt").status_code == 201


def test_same_key_with_another_payload_is_409(client, service, headers, downstream, forgeline):
    first = _post(client, forgeline, headers, key="fl-88213")
    forgeline["git"]["sha"] = "0" * 40

    response = _post(client, forgeline, headers, key="fl-88213")

    assert response.status_code == 409
    error = response.json["error"]
    assert (error["code"], error["details"]) == ("idempotency_conflict",
                                                 {"evaluation_id": first.json["id"]})


@pytest.mark.parametrize("key", ["", "has space", "x" * 129, "naïve"])
def test_malformed_idempotency_key_is_400(client, service, headers, downstream, forgeline, key):
    response = _post(client, forgeline, headers, key=key)

    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_idempotency_key"


def test_losing_a_race_on_the_key_answers_as_replay(
    client, monkeypatch, service, headers, downstream, forgeline
):
    first = _post(client, forgeline, headers, key="race")
    real = idempotency.find_replay
    calls = []

    def missed_once(conn, **kwargs):
        calls.append(kwargs)
        return None if len(calls) == 1 else real(conn, **kwargs)

    monkeypatch.setattr(idempotency, "find_replay", missed_once)
    response = _post(client, forgeline, headers, key="race")

    assert response.status_code == 200 and response.json["id"] == first.json["id"]
    assert len(calls) == 2 and len(downstream.audit) == 1


def test_get_is_scoped_to_the_team(client, factory, service, headers):
    own = factory.evaluation(service)
    foreign = factory.evaluation()

    assert client.get(f"/v1/evaluations/{own.id}", headers=headers).json["id"] == own.id
    response = client.get(f"/v1/evaluations/{foreign.id}", headers=headers)
    assert response.status_code == 404
    reviewer = auth_header(factory.reviewer_key())
    assert client.get(f"/v1/evaluations/{foreign.id}", headers=reviewer).status_code == 200
    assert client.get("/v1/evaluations/999999", headers=reviewer).status_code == 404


def test_list_filters_paginates_and_orders_newest_first(client, factory, team, service, headers):
    webhooks = factory.service(team, "payments-webhooks")
    rows = [factory.evaluation(service, created_at=TODAY - timedelta(hours=h), decision=d,
                               branch=b)
            for h, d, b in [(5, "pass", "main"), (4, "block", "main"), (3, "warn", "release/4")]]
    factory.evaluation(webhooks, decision="block")
    factory.evaluation(decision="block")  # another team

    def ids(query):
        response = client.get(f"/v1/evaluations{query}", headers=headers)
        return [item["id"] for item in response.json["data"]], response.json["meta"]

    assert ids("?service=payments-api") == (
        [r.id for r in reversed(rows)], {"total": 3, "limit": 50, "offset": 0})
    assert ids("?decision=block")[1]["total"] == 2
    assert ids("?branch=release/4")[0] == [rows[2].id]
    assert ids("?service=payments-api&limit=1&offset=1")[0] == [rows[1].id]
    assert client.get("/v1/evaluations?team=ledger-core", headers=headers).status_code == 404
    assert client.get("/v1/evaluations?decision=fail", headers=headers).status_code == 400
    reviewer = auth_header(factory.reviewer_key())
    assert client.get("/v1/evaluations", headers=reviewer).json["meta"]["total"] == 5
    one_team = client.get("/v1/evaluations?team=payments-api", headers=reviewer)
    assert one_team.json["meta"]["total"] == 4
