"""Password hashing, API tokens and session helpers.

These are unit tests of the primitives; the request-level behaviour (login,
logout, role re-reads, token authorisation) is covered in ``test_admin`` and
``test_tenancy``.
"""

from __future__ import annotations

from app.auth import passwords, sessions, tokens


def test_password_hash_round_trip() -> None:
    hashed = passwords.hash_password("correct horse battery staple")
    assert hashed.startswith("pbkdf2:sha256")
    assert passwords.check_password(hashed, "correct horse battery staple")
    assert not passwords.check_password(hashed, "wrong password")


def test_demo_password_shape() -> None:
    assert passwords.demo_password("brightpath", "admin") == "DEMO-brightpath-admin"
    assert passwords.demo_password("tidalbrook", "requester") == "DEMO-tidalbrook-requester"


def test_token_prefix_and_salted_hash() -> None:
    token = tokens.generate_token()
    assert token.startswith("bpk_")
    assert tokens.token_prefix(token) == token[:12]
    assert len(tokens.token_prefix(token)) == 12
    first = tokens.hash_token(token, "salt-one")
    second = tokens.hash_token(token, "salt-two")
    assert first != second
    assert len(first) == 64


def test_parse_bearer() -> None:
    assert tokens.parse_bearer("Bearer abc123") == "abc123"
    assert tokens.parse_bearer("bearer abc123") == "abc123"
    assert tokens.parse_bearer("Basic abc123") is None
    assert tokens.parse_bearer("Bearer   ") is None
    assert tokens.parse_bearer(None) is None


def test_session_lifetime_and_fingerprint() -> None:
    assert sessions.SESSION_LIFETIME_HOURS == 8
    assert sessions.SESSION_COOKIE_NAME == "bellpost_session"
    assert sessions.password_fingerprint("hash-a") != sessions.password_fingerprint("hash-b")
    assert len(sessions.password_fingerprint("hash-a")) == 16
