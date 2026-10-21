from __future__ import annotations

import sys
import types

import pytest
from sqlalchemy import select

from gatekeeper.cli.commands import main
from gatekeeper.core.auth import authenticate
from gatekeeper.core.tables import audit_events, services, teams


@pytest.fixture(autouse=True)
def os_user(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "kwame")


def _fake_module(monkeypatch, name, **functions):
    module = types.ModuleType(name)
    module.__dict__.update(functions)
    monkeypatch.setitem(sys.modules, name, module)


def test_create_team_service_and_key(conn, capsys):
    assert main(["create-team", "fx-options", "--name", "FX Options",
                 "--timezone", "Asia/Singapore"]) == 0
    assert main(["create-service", "fx-options", "options-api"]) == 0
    assert main(["issue-key", "fx-options-ci", "--team", "fx-options"]) == 0
    out = capsys.readouterr().out
    key = out.strip().splitlines()[-1]
    assert "DEMO-whsec-fx-options-" in out
    principal = authenticate(conn, key)
    assert (principal.name, principal.team_slug) == ("fx-options-ci", "fx-options")
    team = conn.execute(select(teams).where(teams.c.slug == "fx-options")).one()
    assert team.timezone == "Asia/Singapore"
    assert conn.execute(select(services.c.name)).scalar() == "Options Api"
    events = conn.execute(select(audit_events.c.action, audit_events.c.actor,
                                 audit_events.c.details).order_by(audit_events.c.id)).all()
    assert [(e.action, e.actor) for e in events] == [
        ("team.created", "cli:kwame"), ("key.issued", "cli:kwame")]
    assert key not in str(events[1].details)


def test_issue_key_refuses_a_duplicate_live_name_and_revoke(conn, factory, capsys):
    factory.team_key(factory.team("ledger-core"))
    assert main(["issue-key", "ledger-core-ci", "--team", "ledger-core"]) == 1
    assert "revoke it first" in capsys.readouterr().err
    assert main(["revoke-key", "ledger-core-ci"]) == 0
    assert main(["revoke-key", "ledger-core-ci"]) == 1


def test_bad_input_is_reported_not_raised(capsys):
    assert main(["create-team", "x-ray", "--name", "X", "--timezone", "Mars/Olympus"]) == 1
    assert main(["create-service", "nope", "svc"]) == 1
    assert "team 'nope' not found" in capsys.readouterr().err


def test_import_policy_calls_publish_policy(monkeypatch, factory, tmp_path, capsys):
    team = factory.team("kyc-platform")
    calls = []

    def publish_policy(conn, **kw):
        calls.append(kw)
        return {"version": 3}

    _fake_module(monkeypatch, "gatekeeper.evaluation.service", publish_policy=publish_policy)
    path = tmp_path / "policy.yaml"
    path.write_text("policy: 1\nrules: []\n")
    assert main(["import-policy", "kyc-platform", str(path), "--comment", "tighten"]) == 0
    assert calls == [{"team_id": team.id, "source": "policy: 1\nrules: []\n",
                      "actor": "cli:kwame", "comment": "tighten"}]
    assert "policy version 3 published" in capsys.readouterr().out


def test_replay_callback_needs_force_for_delivered_rows(monkeypatch, factory, capsys):
    team = factory.team()
    dead = factory.outbox(team, status="dead", attempts=8)
    delivered = factory.outbox(team, status="delivered", attempts=1)
    pending = factory.outbox(team)
    replayed = []
    _fake_module(monkeypatch, "gatekeeper.callbacks.service",
                 replay=lambda conn, **kw: replayed.append(kw["outbox_id"]))
    assert main(["replay-callback", str(dead.id)]) == 0
    assert main(["replay-callback", str(delivered.id)]) == 1
    assert main(["replay-callback", str(pending.id)]) == 1
    assert main(["replay-callback", "--force", str(delivered.id)]) == 0
    assert replayed == [dead.id, delivered.id]
    assert "pass --force" in capsys.readouterr().err
