from __future__ import annotations

import copy

import pytest

from tests.factories import DEFAULT_POLICY, PASSING_EVIDENCE, auth_header

WARN_SECRETS = "policy: 1\nrules:\n  - {id: secrets.allowed, max: 0, action: warn}\n"


@pytest.fixture
def world(factory):
    payments, ledger = factory.team("payments-api"), factory.team("ledger-core")
    factory.service(payments, "payments-api")
    factory.policy(payments)
    factory.policy(ledger)
    return {
        "payments": auth_header(factory.team_key(payments)),
        "ledger": auth_header(factory.team_key(ledger)),
        "reviewer": auth_header(factory.reviewer_key()),
    }


def _dry_run_body(**overrides):
    body = {"service": "payments-api", "branch": "main", "environment": "production",
            "version": "4.12.0", "evidence": copy.deepcopy(PASSING_EVIDENCE)}
    body.update(overrides)
    return body


def test_team_lists_only_its_own_policies(client, world):
    response = client.get("/v1/policies", headers=world["payments"])

    assert response.status_code == 200
    assert [(p["team"], p["version"], p["active"]) for p in response.json["data"]] == [
        ("payments-api", 1, True)]
    assert response.json["meta"] == {"total": 1, "limit": 50, "offset": 0}


@pytest.mark.parametrize(("query", "teams"), [("", {"payments-api", "ledger-core"}),
                                              ("?team=ledger-core", {"ledger-core"})])
def test_reviewer_lists_every_team_or_one(client, world, query, teams):
    response = client.get(f"/v1/policies{query}", headers=world["reviewer"])

    assert {p["team"] for p in response.json["data"]} == teams


@pytest.mark.parametrize("path", ["/v1/policies?team=ledger-core",
                                  "/v1/policies/1?team=ledger-core"])
def test_team_key_cannot_read_another_team(client, world, path):
    assert client.get(path, headers=world["payments"]).status_code == 404


def test_team_key_publishes_its_own_policy(client, world, audit):
    response = client.post("/v1/policies", headers=world["payments"],
                           json={"source": WARN_SECRETS, "comment": "warn on secrets"})

    assert response.status_code == 201
    assert response.json["team"] == "payments-api" and response.json["version"] == 2
    assert response.json["created_by"] == "key:payments-api-ci"
    assert response.json["created_at"] == "2026-12-02T11:00:00+00:00"
    assert audit.events[0]["actor"] == "key:payments-api-ci"
    fetched = client.get("/v1/policies/2", headers=world["payments"]).json
    assert fetched["source"] == WARN_SECRETS and fetched["active"] is True
    assert client.get("/v1/policies/1", headers=world["payments"]).json["active"] is False


def test_team_key_cannot_publish_for_another_team(client, world):
    response = client.post("/v1/policies?team=ledger-core", headers=world["payments"],
                           json={"source": DEFAULT_POLICY})

    assert response.status_code == 404


def test_reviewer_publishes_for_a_named_team(client, world):
    missing = client.post("/v1/policies", headers=world["reviewer"],
                          json={"source": DEFAULT_POLICY})
    named = client.post("/v1/policies?team=ledger-core", headers=world["reviewer"],
                        json={"source": DEFAULT_POLICY})

    assert missing.status_code == 400 and missing.json["error"]["code"] == "bad_request"
    assert named.status_code == 201
    assert (named.json["team"], named.json["created_by"]) == ("ledger-core", "key:security-review")


def test_invalid_policy_is_422_with_every_error(client, world):
    source = "policy: 1\nrules:\n  - {id: secrets.allowed, max: x}\n"
    response = client.post("/v1/policies", headers=world["payments"], json={"source": source})

    assert response.status_code == 422
    error = response.json["error"]
    assert error["code"] == "invalid_policy"
    assert error["details"]["errors"] == [{"path": "rules[0].max",
                                           "message": "must be a whole number >= 0"}]


@pytest.mark.parametrize("body", [{}, {"source": ""}, {"source": DEFAULT_POLICY, "extra": 1}])
def test_malformed_publish_body_is_validation_failed(client, world, body):
    response = client.post("/v1/policies", headers=world["payments"], json=body)

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_failed"


def test_unknown_version_is_404(client, world):
    assert client.get("/v1/policies/9", headers=world["payments"]).status_code == 404


def test_dry_run_against_the_active_policy(client, world):
    body = _dry_run_body()
    body["evidence"]["signing"] = {"signed": True, "verified": False}

    response = client.post("/v1/policies/dry-run", headers=world["payments"], json=body)

    assert response.status_code == 200
    assert response.json["decision"] == "block"
    assert (response.json["policy_version"], response.json["draft"]) == (1, False)
    assert [r["rule"] for r in response.json["reasons"]] == ["signing.required"]
    assert len(response.json["results"]) == 5


def test_dry_run_with_a_draft_writes_nothing(client, world):
    body = _dry_run_body(source=WARN_SECRETS)
    body["evidence"]["secrets"] = {"count": 1, "findings": []}

    response = client.post("/v1/policies/dry-run", headers=world["payments"], json=body)

    assert response.json["decision"] == "warn" and response.json["draft"] is True
    assert response.json["policy_version"] is None
    listed = client.get("/v1/policies", headers=world["payments"]).json
    assert listed["meta"]["total"] == 1


def test_dry_run_with_missing_evidence_kind(client, world):
    body = _dry_run_body(evidence={})

    response = client.post("/v1/policies/dry-run", headers=world["payments"], json=body)

    assert response.json["decision"] == "block"
    assert all(r["details"] == {"missing": True} for r in response.json["reasons"])


@pytest.mark.parametrize(
    ("overrides", "status", "code"),
    [
        ({"service": "refunds-worker"}, 422, "unknown_service"),
        ({"environment": "prod"}, 422, "validation_failed"),
        ({"evidence": {"sbom": {}}}, 422, "validation_failed"),
        ({"evidence": {"secrets": {"count": 0, "findings": [{"detector": "d", "path": "p"}]}}},
         422, "validation_failed"),
        ({"evidence": {"tests": {"passed": "10", "failed": 0, "skipped": 0}}},
         422, "validation_failed"),
        ({"evidence": {"dependencies": {"packages": [
            {"name": "a", "version": "1", "vulnerabilities": [{"id": "X", "severity": "HIGH"}]},
        ]}}}, 422, "validation_failed"),
        ({"source": "policy: 1\nrules: oops\n"}, 422, "invalid_policy"),
    ],
)
def test_dry_run_rejects_bad_input(client, world, overrides, status, code):
    response = client.post("/v1/policies/dry-run", headers=world["payments"],
                           json=_dry_run_body(**overrides))

    assert response.status_code == status
    assert response.json["error"]["code"] == code


def test_reviewer_dry_run_needs_a_team(client, world):
    response = client.post("/v1/policies/dry-run", headers=world["reviewer"], json=_dry_run_body())
    named = client.post("/v1/policies/dry-run?team=payments-api", headers=world["reviewer"],
                        json=_dry_run_body())

    assert response.status_code == 400
    assert named.status_code == 200 and named.json["decision"] == "pass"
