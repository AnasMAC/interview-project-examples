from __future__ import annotations

import pytest
from sqlalchemy import func, select

from gatekeeper.core.errors import NotFound, ValidationFailed
from gatekeeper.core.tables import policies
from gatekeeper.evaluation import service
from tests.evaluation.conftest import make_submission
from tests.factories import DEFAULT_POLICY, PASSING_EVIDENCE, TODAY

WARN_SECRETS = "policy: 1\nrules:\n  - {id: secrets.allowed, max: 0, action: warn}\n"
LEAKY = {**PASSING_EVIDENCE, "secrets": {"count": 2, "findings": []}}


@pytest.fixture
def svc(factory):
    return factory.service(factory.team("payments-api"), "payments-api")


def _evaluate(conn, svc, evidence=None, **overrides):
    return service.evaluate(conn, team_id=svc.team_id, service_id=svc.id,
                            submission=make_submission(evidence, **overrides))


def test_team_without_policy_gets_policy_missing_warning(conn, svc, waivers):
    decision = _evaluate(conn, svc)

    assert decision.decision == "warn"
    assert (decision.policy_id, decision.policy_version) == (None, None)
    assert decision.reasons == [{
        "rule": "policy.missing", "outcome": "warn", "waiver_id": None, "details": {},
        "message": "team has no policy; publish one with POST /v1/policies",
    }]
    assert waivers.calls == []


def test_evaluate_uses_the_highest_version(conn, factory, svc):
    team = factory.team_of(svc)
    factory.policy(team, WARN_SECRETS)
    latest = factory.policy(team, DEFAULT_POLICY)

    decision = _evaluate(conn, svc, LEAKY)

    assert (decision.decision, decision.policy_id, decision.policy_version) == (
        "block", latest.id, 2)
    assert [r["rule"] for r in decision.reasons] == ["secrets.allowed"]


def test_passing_submission_does_not_query_waivers(conn, factory, svc, waivers):
    factory.policy(factory.team_of(svc))

    decision = _evaluate(conn, svc)

    assert decision.decision == "pass" and decision.reasons == []
    assert len(decision.results) == 5
    assert waivers.calls == []


def test_waived_block_becomes_warn_with_waiver_id(conn, factory, svc, waivers):
    factory.policy(factory.team_of(svc))
    waivers.covered["secrets.allowed"] = 41

    decision = _evaluate(conn, svc, LEAKY, version="4.12.0")

    assert decision.decision == "warn"
    assert decision.reasons[0]["waiver_id"] == 41
    assert decision.reasons[0]["message"] == "waived: 2 secret findings (max 0)"
    assert waivers.calls == [{"team_id": svc.team_id, "service_id": svc.id, "version": "4.12.0",
                              "rules": [r.rule for r in decision.results]}]


def test_unwaived_block_still_wins_over_a_waived_one(conn, factory, svc, waivers):
    factory.policy(factory.team_of(svc))
    waivers.covered["secrets.allowed"] = 41
    evidence = {**LEAKY, "signing": {"signed": False, "verified": False, "key_id": None}}

    decision = _evaluate(conn, svc, evidence)

    assert decision.decision == "block"
    assert [(r["rule"], r["outcome"], r["waiver_id"]) for r in decision.reasons] == [
        ("secrets.allowed", "warn", 41), ("signing.required", "block", None),
    ]


def test_publish_inserts_next_version_and_audits(conn, factory, svc, audit):
    team = factory.team_of(svc)
    factory.policy(team)

    view = service.publish_policy(conn, team_id=team.id, source=WARN_SECRETS,
                                  actor="key:payments-api-ci", comment="relax secrets")

    assert view == {
        "id": view["id"], "team": "payments-api", "version": 2, "active": True,
        "comment": "relax secrets", "created_by": "key:payments-api-ci",
        "created_at": TODAY.isoformat(), "source": WARN_SECRETS, "warnings": [],
    }
    assert audit.events == [{
        "action": "policy.published", "actor": "key:payments-api-ci", "subject_type": "policy",
        "subject_id": view["id"], "team_id": team.id,
        "details": {"version": 2, "comment": "relax secrets"},
    }]


def test_publish_reports_deprecation_warnings(conn, factory):
    team = factory.team()

    view = service.publish_policy(conn, team_id=team.id, actor="cli:grace",
                                  source="policy: 1\nrules:\n  - {id: sast.max_high, max: 1}\n")

    assert view["version"] == 1
    assert view["warnings"] == ["rules[0]: sast.max_high is deprecated, use sast.new_high_max"]


def test_invalid_publish_stores_and_audits_nothing(conn, factory, audit):
    team = factory.team()

    with pytest.raises(ValidationFailed) as excinfo:
        service.publish_policy(conn, team_id=team.id, source="policy: 1\nrules: []\n",
                               actor="key:x")

    assert excinfo.value.code == "invalid_policy"
    assert conn.execute(select(func.count()).select_from(policies)).scalar() == 0
    assert audit.events == []


def test_publish_for_unknown_team_is_404(conn):
    with pytest.raises(NotFound):
        service.publish_policy(conn, team_id=999_999, source=DEFAULT_POLICY, actor="key:x")


def test_publish_takes_effect_on_the_next_evaluation(conn, factory, svc, policy_cache):
    factory.policy(factory.team_of(svc))
    assert _evaluate(conn, svc, LEAKY).decision == "block"
    assert (svc.team_id, 1) in policy_cache

    service.publish_policy(conn, team_id=svc.team_id, source=WARN_SECRETS, actor="key:x")

    assert (svc.team_id, 1) not in policy_cache
    decision = _evaluate(conn, svc, LEAKY)
    assert (decision.decision, decision.policy_version) == ("warn", 2)


def test_version_published_elsewhere_is_seen_without_invalidation(conn, factory, svc):
    """Another gunicorn worker published: this worker's cache was never told."""
    team = factory.team_of(svc)
    factory.policy(team)
    _evaluate(conn, svc, LEAKY)

    factory.policy(team, WARN_SECRETS)

    assert _evaluate(conn, svc, LEAKY).policy_version == 2


def test_dry_run_against_active_policy_and_draft(conn, factory, svc, policy_cache):
    factory.policy(factory.team_of(svc))
    submission = make_submission(LEAKY)
    args = {"team_id": svc.team_id, "service_id": svc.id, "submission": submission}

    active = service.dry_run(conn, **args)
    draft = service.dry_run(conn, **args, source=WARN_SECRETS)

    assert (active.decision, active.policy_version) == ("block", 1)
    assert (draft.decision, draft.policy_id, draft.policy_version) == ("warn", None, None)
    assert len(policy_cache) == 1  # the draft is not cached
    assert conn.execute(select(func.count()).select_from(policies)).scalar() == 1


def test_dry_run_applies_waivers_and_rejects_invalid_drafts(conn, factory, svc, waivers):
    waivers.covered["secrets.allowed"] = 7
    args = {"team_id": svc.team_id, "service_id": svc.id, "submission": make_submission(LEAKY)}

    assert service.dry_run(conn, **args, source=DEFAULT_POLICY).decision == "warn"
    with pytest.raises(ValidationFailed):
        service.dry_run(conn, **args, source="policy: 1\nrules:\n  - {id: nope}\n")


def test_get_and_list_mark_only_the_latest_version_active(conn, factory):
    team, other = factory.team("payments-api"), factory.team("ledger-core")
    factory.policy(team, created_at=TODAY.replace(month=10))
    factory.policy(team, created_at=TODAY.replace(month=11))
    factory.policy(other)

    items, total = service.list_policies(conn, team_id=team.id, limit=50, offset=0)
    everything, all_total = service.list_policies(conn, team_id=None, limit=1, offset=0)

    assert [(i["version"], i["active"]) for i in items] == [(2, True), (1, False)]
    assert total == 2 and "source" not in items[0]
    assert all_total == 3 and len(everything) == 1
    assert service.get_policy(conn, team_id=team.id, version=1)["active"] is False
    with pytest.raises(NotFound):
        service.get_policy(conn, team_id=other.id, version=2)
