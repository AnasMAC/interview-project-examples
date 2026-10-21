"""End to end with the real packages and real commits: policy, waiver, CI
evaluations (Forgeline v2 and legacy), idempotency, the scheduler's jobs and
the reports. Only the HTTP call of callback delivery is replaced."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from gatekeeper.callbacks import delivery
from gatekeeper.callbacks.signing import verify
from gatekeeper.core.tables import audit_events, callback_outbox, waivers
from gatekeeper.scheduler.runner import Scheduler
from tests.factories import DEFAULT_POLICY, TODAY, Factory, auth_header

EXPIRY = datetime(2026, 12, 3, 1, 0, tzinfo=UTC)  # 09:00 in Singapore
CALLBACK = "http://ci-mock:9100/callbacks/payments-api/payments-api"
FORGELINE = {
    "schema": "forgeline/v2", "pipeline": {"id": "fl-90001"},
    "project": {"service": "payments-api"},
    "git": {"sha": "c41e0a9b7d2f6e15a8c3b90d4e7f21a6b5c8d903", "ref": "refs/heads/main"},
    "deploy": {"environment": "production", "version": "4.12.3"},
    "callback": {"url": CALLBACK},
    "evidence": {
        "dependencies": [{"name": "ledgerkit", "version": "2.4.1", "ecosystem": "pypi",
                          "advisories": [{"id": "MBSA-2026-0141", "severity": "CRITICAL"}]}],
        "secrets_scan": {"findings": []}, "sast": {"new_findings": {"high": 1}},
        "tests": {"passed": 412, "failed": 0, "skipped": 6},
        "signing": {"signed": True, "verified": True, "key_id": "mossbank-release-2026"},
    },
}
LEGACY = {
    "runner": "legacy-runner/1.8", "service_name": "refunds-worker", "build_id": "LR-1",
    "git_commit": "4be1c0ffee" * 4, "git_branch": "main", "deploy_env": "prod",
    "app_version": "1.9.4", "secrets_found": 0, "sast_high_new": 0, "tests_total": 120,
    "tests_failed": 0, "signed": "yes",
    "vulns": [{"package": "pdfmint", "installed": "0.9.2", "id": "MBSA-2025-0310", "sev": "SEV1"}],
}


def _rows(engine, table, *where):
    with engine.connect() as c:
        return c.execute(select(table).where(*where).order_by(table.c.id)).all()


@pytest.mark.committed
def test_release_gate_end_to_end(committed_engine, app, frozen_clock, monkeypatch):
    with committed_engine.begin() as c:
        f = Factory(c)
        payments = f.team("payments-api")
        f.service(payments, "payments-api")
        f.service(payments, "refunds-worker")
        singapore = f.team("settlement-sg", timezone="Asia/Singapore",
                           notify_url="http://ci-mock:9100/notify/settlement-sg")
        noticed = f.waiver(team=singapore, rule="tests.min_pass_rate",
                           expires_at=EXPIRY + timedelta(hours=23))
        team, reviewer = auth_header(f.team_key(payments)), auth_header(f.reviewer_key())
    client = app.test_client()

    source = DEFAULT_POLICY.replace("sast.new_high_max", "sast.max_high")
    published = client.post("/v1/policies?team=payments-api", headers=reviewer,
                            json={"source": source, "comment": "first"})
    assert published.status_code == 201 and published.json["version"] == 1
    assert published.json["warnings"] == ["rules[2]: sast.max_high is deprecated, "
                                          "use sast.new_high_max"]
    waiver = client.post("/v1/waivers", headers=team, json={
        "service": "payments-api", "rule": "dependency.max_severity",
        "version_range": ">=4.12.0,<4.13.0", "expires_at": EXPIRY.isoformat(),
        "reason": "ledgerkit 2.4.1 has no fixed release yet"}).json
    assert client.post(f"/v1/waivers/{waiver['id']}/approve", headers=reviewer,
                       json={}).json["status"] == "approved"

    # Forgeline v2: the waived dependency violation and the SAST finding both warn.
    keyed = {**team, "Idempotency-Key": "fl-90001:1"}
    evaluation = client.post("/v1/evaluations", headers=keyed, json=FORGELINE).json
    assert evaluation["decision"] == "warn" and evaluation["policy_version"] == 1
    assert [(r["rule"], r["outcome"], r["waiver_id"]) for r in evaluation["reasons"]] == [
        ("dependency.max_severity", "warn", waiver["id"]), ("sast.new_high_max", "warn", None)]
    assert evaluation["reasons"][0]["message"].startswith("waived: ledgerkit 2.4.1")
    trail = {e.action: e for e in _rows(committed_engine, audit_events,
                                        audit_events.c.created_at == TODAY)}
    assert trail["evaluation.decided"].details["waiver_ids"] == [waiver["id"]]
    assert (trail["waiver.applied"].subject_id, trail["waiver.applied"].details) == (
        waiver["id"], {"evaluation_id": evaluation["id"], "rule": "dependency.max_severity"})
    assert [(o.evaluation_id, o.status, o.url) for o in _rows(committed_engine, callback_outbox)
            ] == [(evaluation["id"], "pending", CALLBACK)]

    # Legacy runner, another service: not covered by the waiver, blocks; no callback.
    legacy = client.post("/v1/evaluations", headers=team, json=LEGACY)
    assert legacy.status_code == 201 and legacy.json["decision"] == "block"
    assert legacy.json["source"] == "legacy" and legacy.json["reasons"][0]["waiver_id"] is None

    # Idempotency: replay answers the stored decision, a changed payload is a conflict.
    replay = client.post("/v1/evaluations", headers=keyed, json=FORGELINE)
    assert replay.status_code == 200 and replay.headers["Idempotent-Replay"] == "true"
    assert replay.json == evaluation
    changed = copy.deepcopy(FORGELINE)
    changed["deploy"]["version"] = "4.12.4"
    conflict = client.post("/v1/evaluations", headers=keyed, json=changed)
    assert (conflict.status_code, conflict.json["error"]["details"]) == (
        409, {"evaluation_id": evaluation["id"]})
    assert len(_rows(committed_engine, callback_outbox)) == 1
    assert len(_rows(committed_engine, audit_events,
                     audit_events.c.action == "evaluation.decided")) == 2

    # Scheduler: callbacks now; the waiver at its exact instant, 09:00 Singapore notice.
    sent = []
    monkeypatch.setattr(delivery, "post", lambda url, body, headers, timeout_s:
                        sent.append((url, body, headers)) or 204)
    scheduler = Scheduler(committed_engine)
    try:
        assert scheduler.tick()
        url, body, headers = sent[0]
        assert url == CALLBACK and json.loads(body)["evaluation"] == evaluation
        assert verify(payments.callback_secret, int(headers["X-Gatekeeper-Timestamp"]), body,
                      headers["X-Gatekeeper-Signature"], now=int(TODAY.timestamp()))
        frozen_clock.freeze(EXPIRY - timedelta(seconds=1))
        assert scheduler.tick() and len(sent) == 1
        assert _rows(committed_engine, waivers, waivers.c.id == waiver["id"])[0].status == (
            "approved")
        frozen_clock.advance(seconds=1)
        assert scheduler.tick()
    finally:
        scheduler.release()
    assert _rows(committed_engine, waivers, waivers.c.id == waiver["id"])[0].status == "expired"
    assert _rows(committed_engine, audit_events, audit_events.c.action == "waiver.expired",
                 audit_events.c.subject_id == waiver["id"])
    assert [(u, h["X-Gatekeeper-Event"]) for u, _, h in sent[1:]] == [
        ("http://ci-mock:9100/notify/settlement-sg", "waiver.expiring")]
    assert json.loads(sent[1][1])["waiver"]["id"] == noticed.id
    assert {o.status for o in _rows(committed_engine, callback_outbox)} == {"delivered"}

    # The expired waiver no longer covers the same build.
    again = client.post("/v1/evaluations", headers=team, json=FORGELINE)
    assert again.json["decision"] == "block"

    window = "team=payments-api&days=7&until=2026-12-04T00:00:00%2B00:00"
    card = client.get(f"/v1/reports/scorecard?{window}", headers=reviewer).json["teams"][0]
    assert (card["evaluations"], card["decisions"]) == (3, {"pass": 0, "warn": 1, "block": 2})
    assert card["waivers"]["requested_in_window"] == 1 and card["waivers"]["active"] == 0
    assert card["top_failing_rules"][0] == {"rule": "dependency.max_severity", "count": 3,
                                            "block": 2, "warn": 1, "waived": 1}
    csv = client.get(f"/v1/reports/export.csv?{window}", headers=reviewer)
    lines = csv.get_data(as_text=True).splitlines()
    assert lines[0].startswith("id,created_at,team,service") and len(lines) == 4
    assert lines[1].endswith(f",warn,1,dependency.max_severity;sast.new_high_max,{waiver['id']}")
