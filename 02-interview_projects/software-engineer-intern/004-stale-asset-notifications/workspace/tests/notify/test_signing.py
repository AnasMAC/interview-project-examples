import pytest

from atlas.notify.signing import sign, verify

SECRET = "DEMO-whsec-orchid-grid-3897bfee30d5"
BODY = b'{"event":"exposure.opened","id":"evt_9"}'
T = 1793889000  # 2026-11-05T14:30:00Z


def test_sign_matches_the_documented_scheme():
    # Known vector: HMAC-SHA256(secret, b"1." + b"") computed outside Atlas.
    assert sign(SECRET, b"", 1) == "t=1,v1=bd3d6a4fcf6263b456eba28b12627a201334949531c633d0a2ffa21ff9f8d1c5"


@pytest.mark.parametrize(("body", "header", "now", "ok"), [
    (BODY, sign(SECRET, BODY, T), T + 300, True),
    (BODY, sign(SECRET, BODY, T), T + 301, False),  # replay window
    (BODY, sign(SECRET, BODY, T), T - 301, False),  # from the future
    (BODY + b" ", sign(SECRET, BODY, T), T, False),  # re-serialized body
    (BODY, sign("other", BODY, T), T, False),
    (BODY, f"t={T},v1=deadbeef,{sign(SECRET, BODY, T).split(',')[1]}", T, True),  # rotation
    (BODY, "v1=abc", T, False),
    (BODY, "t=soon,v1=abc", T, False),
    (BODY, "", T, False),
])
def test_verify(body, header, now, ok):
    assert verify(SECRET, body, header, now=now) is ok

