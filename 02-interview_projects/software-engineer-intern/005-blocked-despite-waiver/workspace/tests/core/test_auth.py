from __future__ import annotations

import pytest
from flask import Flask, g

from gatekeeper.core import auth
from gatekeeper.core.errors import Forbidden, NotFound
from tests.factories import auth_header


def test_issued_key_authenticates_and_only_the_hash_is_stored(conn, factory):
    team = factory.team("payments-api")
    key_id, key = auth.issue_key(conn, name="forgeline", role=auth.ROLE_TEAM, team_id=team.id)

    principal = auth.authenticate(conn, key)

    assert key.startswith("gk_demo_") and len(key) == 40
    assert principal == auth.Principal(key_id, "forgeline", "team", team.id, "payments-api")
    stored = conn.exec_driver_sql("SELECT prefix, key_hash FROM api_keys").one()
    assert stored.prefix == key[:16] and stored.key_hash == auth.hash_key(key) != key


def test_same_prefix_with_wrong_secret_part_is_rejected(conn, factory):
    key = factory.team_key()
    tampered = key[:-1] + ("a" if key[-1] != "a" else "b")

    assert auth.authenticate(conn, tampered) is None
    assert auth.authenticate(conn, "not-a-gatekeeper-key") is None


def test_revoked_key_is_rejected(conn, factory):
    key_id, key = auth.issue_key(conn, name="old", role=auth.ROLE_REVIEWER)

    assert auth.revoke_key(conn, key_id) is True
    assert auth.authenticate(conn, key) is None
    assert auth.revoke_key(conn, key_id) is False


@pytest.mark.parametrize(
    ("role", "team_id"), [("team", None), ("security_reviewer", 1), ("admin", None)]
)
def test_issue_key_refuses_inconsistent_role_and_team(conn, role, team_id):
    with pytest.raises(ValueError):
        auth.issue_key(conn, name="x", role=role, team_id=team_id)


@pytest.mark.parametrize(
    ("header", "code"),
    [(None, "missing_api_key"), ("Basic abc", "missing_api_key"),
     ("Bearer gk_demo_0000000000000000000000000000000", "invalid_api_key")],
)
def test_requests_without_a_valid_key_get_401(client, header, code):
    headers = {"Authorization": header} if header else {}

    response = client.get("/v1/whoami", headers=headers)

    assert response.status_code == 401
    assert response.json["error"]["code"] == code
    assert response.headers["WWW-Authenticate"].startswith("Bearer")


def test_whoami_reports_team_and_reviewer_principals(client, factory):
    team_key = factory.team_key(factory.team("ledger-core"), name="ledger-ci")
    reviewer_key = factory.reviewer_key("grace.adeyemi")

    assert client.get("/v1/whoami", headers=auth_header(team_key)).json == {
        "key": "ledger-ci", "role": "team", "team": "ledger-core"}
    assert client.get("/v1/whoami", headers=auth_header(reviewer_key)).json == {
        "key": "grace.adeyemi", "role": "security_reviewer", "team": None}


@pytest.fixture
def as_principal():
    app = Flask(__name__)

    def _use(principal: auth.Principal):
        ctx = app.test_request_context()
        ctx.push()
        g.principal = principal
        return ctx

    contexts = []
    yield lambda p: contexts.append(_use(p))
    for ctx in reversed(contexts):
        ctx.pop()


def test_team_scope_pins_team_keys_to_their_own_team(conn, factory, as_principal):
    own, other = factory.team("fx-rates"), factory.team("card-issuing")
    as_principal(auth.Principal(1, "fx-ci", "team", own.id, own.slug))

    assert auth.team_scope(conn, None) == own.id
    assert auth.team_scope(conn, "fx-rates") == own.id
    with pytest.raises(NotFound):
        auth.team_scope(conn, other.slug)
    with pytest.raises(NotFound):
        auth.ensure_team_access(other.id, "waiver 3")
    auth.ensure_team_access(own.id, "waiver 3")


def test_team_scope_for_reviewers(conn, factory, as_principal):
    team = factory.team("risk-scoring")
    as_principal(auth.Principal(2, "grace.adeyemi", "security_reviewer", None, None))

    assert auth.team_scope(conn, None) is None
    assert auth.team_scope(conn, "risk-scoring") == team.id
    with pytest.raises(NotFound):
        auth.team_scope(conn, "no-such-team")
    auth.ensure_team_access(team.id, "waiver 3")


def test_require_role(as_principal):
    @auth.require_role(auth.ROLE_REVIEWER)
    def approve():
        return "approved"

    as_principal(auth.Principal(1, "ci", "team", 1, "payments-api"))
    with pytest.raises(Forbidden) as excinfo:
        approve()
    assert excinfo.value.code == "role_required"

    as_principal(auth.Principal(2, "grace.adeyemi", "security_reviewer", None, None))
    assert approve() == "approved"
