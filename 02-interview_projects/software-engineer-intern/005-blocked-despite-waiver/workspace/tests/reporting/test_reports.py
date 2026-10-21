from __future__ import annotations

import csv
import io
from datetime import timedelta

from tests.factories import TODAY, auth_header


def _reason(rule, outcome, waiver_id=None):
    return {"rule": rule, "outcome": outcome, "message": "m", "waiver_id": waiver_id,
            "details": {}}


def _seed(factory):
    team = factory.team("payments-api")
    service = factory.service(team, "payments-api")
    other = factory.service(factory.team("fx-rates"), "rates-api")
    waiver = factory.waiver(team, service, created_at=TODAY - timedelta(days=10))
    factory.waiver(team, status="pending")
    factory.evaluation(service, decision="pass")
    factory.evaluation(service, decision="block", reasons=[
        _reason("dependency.max_severity", "block"), _reason("sast.new_high_max", "warn")])
    factory.evaluation(service, decision="warn",
                       reasons=[_reason("dependency.max_severity", "warn", waiver.id)])
    factory.evaluation(service, decision="block", created_at=TODAY - timedelta(days=40),
                       reasons=[_reason("secrets.allowed", "block")])
    factory.evaluation(other, decision="block", branch="=HYPERLINK(1)",
                       reasons=[_reason("tests.min_pass_rate", "block")])
    return team, waiver


def test_scorecard_counts_rates_rules_and_waivers(client, factory):
    team, waiver = _seed(factory)
    response = client.get("/v1/reports/scorecard?days=28",
                          headers=auth_header(factory.reviewer_key()))
    assert response.status_code == 200
    cards = {c["team"]: c for c in response.json["teams"]}
    assert set(cards) == {"payments-api", "fx-rates"}
    card = cards["payments-api"]
    assert card["evaluations"] == 3
    assert card["decisions"] == {"pass": 1, "warn": 1, "block": 1}
    assert card["block_rate"] == 0.3333
    assert card["top_failing_rules"][0] == {
        "rule": "dependency.max_severity", "count": 2, "block": 1, "warn": 1, "waived": 1}
    assert [r["rule"] for r in card["top_failing_rules"]] == [
        "dependency.max_severity", "sast.new_high_max"]
    assert card["waivers"]["active"] == 1
    assert card["waivers"]["pending"] == 1
    assert card["waivers"]["median_active_age_days"] == 10.0


def test_team_key_sees_only_its_own_team(client, factory):
    team, _ = _seed(factory)
    headers = auth_header(factory.team_key(team))
    response = client.get("/v1/reports/scorecard", headers=headers)
    assert [c["team"] for c in response.json["teams"]] == ["payments-api"]
    assert client.get("/v1/reports/scorecard?team=fx-rates", headers=headers).status_code == 404
    assert client.get("/v1/reports/export.csv?team=fx-rates", headers=headers).status_code == 404


def test_export_csv_rows_and_formula_guard(client, factory):
    _seed(factory)
    response = client.get("/v1/reports/export.csv?days=28&decision=block",
                          headers=auth_header(factory.reviewer_key()))
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
    assert [(r["team"], r["rules"]) for r in rows] == [
        ("payments-api", "dependency.max_severity;sast.new_high_max"),
        ("fx-rates", "tests.min_pass_rate"),
    ]
    assert rows[1]["branch"] == "'=HYPERLINK(1)"


def test_window_validation(client, factory):
    headers = auth_header(factory.reviewer_key())
    assert client.get("/v1/reports/scorecard?days=0", headers=headers).status_code == 400
    response = client.get("/v1/reports/export.csv?until=2026-12-01T00:00:00", headers=headers)
    assert response.json["error"]["code"] == "invalid_datetime"
