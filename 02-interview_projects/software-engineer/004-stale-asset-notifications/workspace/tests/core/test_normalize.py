import pytest

from atlas.core import normalize
from atlas.core.normalize import NormalizationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("WWW.Harborview-Bank.example.test", "www.harborview-bank.example.test"),
        ("  api.orchid-grid.example.test.  ", "api.orchid-grid.example.test"),
        ("bücher.quillstone-media.example.test", "xn--bcher-kva.quillstone-media.example.test"),
        ("BÜCHER.quillstone-media.example.test", "xn--bcher-kva.quillstone-media.example.test"),
        ("straße.example.test", "xn--strae-oqa.example.test"),  # IDNA 2008, not "strasse"
        ("_dmarc.harborview-bank.example.test", "_dmarc.harborview-bank.example.test"),
    ],
)
def test_normalize_hostname(raw, expected):
    assert normalize.normalize_hostname(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", ".", "a..example.test", "www.example.test..", "-bad.example.test", "a b.example.test",
            "*.example.test", "x." + "a" * 64 + ".test", ("a" * 60 + ".") * 5 + "test"],
)
def test_normalize_hostname_rejects(raw):
    with pytest.raises(NormalizationError):
        normalize.normalize_hostname(raw)


def test_wildcard_only_as_first_label_when_allowed():
    assert normalize.normalize_hostname("*.CDN.example.test", allow_wildcard=True) == "*.cdn.example.test"
    with pytest.raises(NormalizationError):
        normalize.normalize_hostname("www.*.example.test", allow_wildcard=True)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("198.51.100.7", "198.51.100.7"),
        ("2001:0DB8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ("[2001:db8::10]", "2001:db8::10"),
        ("::ffff:203.0.113.9", "203.0.113.9"),
    ],
)
def test_normalize_ip(raw, expected):
    assert normalize.normalize_ip(raw) == expected


@pytest.mark.parametrize("raw", ["198.51.100", "010.1.1.1", "fe80::1%eth0", "host.example.test"])
def test_normalize_ip_rejects(raw):
    with pytest.raises(NormalizationError):
        normalize.normalize_ip(raw)


def test_normalize_cidr_clears_host_bits():
    assert normalize.normalize_cidr("10.20.3.4/16") == "10.20.0.0/16"
    assert normalize.normalize_cidr("2001:DB8:0:1::/48") == "2001:db8::/48"
    with pytest.raises(NormalizationError):
        normalize.normalize_cidr("10.0.0.0/33")


def test_ip_in_network():
    assert normalize.ip_in_network("10.20.255.1", "10.20.0.0/16")
    assert not normalize.ip_in_network("10.21.0.1", "10.20.0.0/16")
    assert normalize.ip_in_network("2001:db8::abcd", "2001:db8::/32")
    assert not normalize.ip_in_network("::ffff:10.20.0.1", "2001:db8::/32")  # mapped -> IPv4


@pytest.mark.parametrize(
    ("ip", "public"),
    [("203.0.113.10", True), ("2001:db8::5", True), ("10.4.0.9", False), ("100.64.1.1", False),
     ("172.31.0.1", False), ("127.0.0.1", False), ("fd00::1", False), ("169.254.1.1", False)],
)
def test_is_public_ip(ip, public):
    assert normalize.is_public_ip(ip) is public
