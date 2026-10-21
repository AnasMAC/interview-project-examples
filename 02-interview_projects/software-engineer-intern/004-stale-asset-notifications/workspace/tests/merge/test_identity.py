import pytest

from atlas.core.normalize import NormalizationError
from atlas.merge.certificates import covered_names, hostname_matches
from atlas.merge.identity import identity_key

FINGERPRINT = "ab" * 32


@pytest.mark.parametrize(
    ("kind", "value", "key"),
    [
        ("host", " WWW.Harborview-Bank.example.test. ", "www.harborview-bank.example.test"),
        ("domain", "Straße.example.test", "xn--strae-oqa.example.test"),
        ("ip", "::ffff:198.51.100.7", "198.51.100.7"),
        ("ip", "2001:DB8:0:0::1", "2001:db8::1"),
        ("network", "10.20.30.40/16", "10.20.0.0/16"),
        ("certificate", ":".join(["AB"] * 32), FINGERPRINT),
        ("cloud_resource", "Nimbus:4471-2210-0093:VM-0a1b", "nimbus:4471-2210-0093:vm-0a1b"),
    ],
)
def test_identity_key_is_canonical(kind, value, key):
    assert identity_key(kind, value) == key


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("host", "bad..example.test"),
        ("host", "*.example.test"),  # wildcards are certificate names, never host assets
        ("ip", "198.51.100.300"),
        ("certificate", "ab" * 20),  # SHA-1 sized
        ("cloud_resource", "aws:1:2"),
        ("cloud_resource", "nimbus::vm-1"),
        ("printer", "x"),
    ],
)
def test_identity_key_rejects(kind, value):
    with pytest.raises(NormalizationError):
        identity_key(kind, value)


@pytest.mark.parametrize(
    ("pattern", "hostname", "expected"),
    [
        ("*.a.test", "x.a.test", True),
        ("*.A.test.", "X.a.TEST", True),
        ("*.a.test", "a.test", False),  # not the apex
        ("*.a.test", "y.x.a.test", False),  # one label only
        ("*.a.test", "xa.test", False),
        ("www.a.test", "WWW.A.test.", True),
        ("www.a.test", "api.a.test", False),
        ("x.*.a.test", "x.y.a.test", False),
        ("*.a.test", "not a hostname", False),
    ],
)
def test_hostname_matches_one_label_wildcards(pattern, hostname, expected):
    assert hostname_matches(pattern, hostname) is expected


def test_covered_names_normalizes_and_drops_garbage():
    attributes = {"sans": ["WWW.a.test.", "www.a.test", "*.a.test", "bad..name"], "subject_cn": "cn.a.test"}
    assert covered_names(attributes) == ["www.a.test", "*.a.test"]
    assert covered_names({}) == []
