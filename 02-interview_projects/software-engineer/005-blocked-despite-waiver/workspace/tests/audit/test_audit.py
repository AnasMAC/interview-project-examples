from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from gatekeeper.audit.service import record
from gatekeeper.core.tables import audit_events
from tests.factories import TODAY, auth_header


def test_record_writes_in_the_callers_transaction(conn, factory):
    team = factory.team()
    event_id = record(conn, action="waiver.applied", actor="key:payments-api-ci",
                      subject_type="waiver", subject_id=41, team_id=team.id,
                      details={"evaluation_id": 8123, "rule": "sast.new_high_max"})

    row = conn.execute(select(audit_events).where(audit_events.c.id == event_id)).one()
    assert (row.action, row.subject_id, row.created_at) == ("waiver.applied", 41, TODAY)
    assert row.details == {"evaluation_id": 8123, "rule": "sast.new_high_max"}


def test_list_filters_scopes_and_paginates(client, factory):
    payments, ledger = factory.team("payments-api"), factory.team("ledger-core")
    for hours in (1, 2, 3):
        factory.audit_event(payments, action="evaluation.decided", subject_type="evaluation",
                            subject_id=hours, created_at=TODAY - timedelta(hours=hours))
    factory.audit_event(ledger, created_at=TODAY - timedelta(hours=1))
    factory.audit_event(None, action="key.issued", subject_type="api_key")
    team_key = auth_header(factory.team_key(payments))
    reviewer = auth_header(factory.reviewer_key())

    page = client.get("/v1/audit?limit=2&since=2026-12-02T08:00:00%2B00:00",
                      headers=team_key).json
    assert [e["subject_id"] for e in page["data"]] == [1, 2]
    assert page["meta"] == {"total": 3, "limit": 2, "offset": 0}
    assert page["data"][0]["team"] == "payments-api"
    assert client.get("/v1/audit", headers=reviewer).json["meta"]["total"] == 5
    only = client.get("/v1/audit?team=ledger-core&action=policy.published", headers=reviewer)
    assert only.json["meta"]["total"] == 1
    assert client.get("/v1/audit?team=ledger-core", headers=team_key).status_code == 404


def test_naive_query_datetimes_are_rejected(client, factory):
    response = client.get("/v1/audit?until=2026-12-02T11:00:00",
                          headers=auth_header(factory.reviewer_key()))

    assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_datetime")
