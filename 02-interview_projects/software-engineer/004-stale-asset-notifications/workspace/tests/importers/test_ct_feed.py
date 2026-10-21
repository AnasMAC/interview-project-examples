import base64
import hashlib
import json
import re
from datetime import UTC, datetime

import pytest

from atlas.importers import ct_feed
from atlas.importers.base import ImportFormatError, ObservedLink
from tests.factories import TODAY
from tests.importers.helpers import fixture_text

HVB = "harborview-bank.example.test"


def _by_cn(batch) -> dict:
    return {o.attributes["subject_cn"]: o for o in batch.observations}


def _line(cert: dict, **entry) -> str:
    defaults = {"log": "argon2026h2", "index": 1, "type": "x509", "seen": "2026-11-01T00:00:00Z"}
    return json.dumps(defaults | entry | {"cert": cert})


CERT = {
    "fingerprint_sha256": "ab" * 32,
    "serial": "01",
    "issuer": {"cn": "Lumen Trust RSA CA 2025"},
    "subject": {"cn": "www.example.test"},
    "not_before": "2026-01-01T00:00:00Z",
    "not_after": "2027-01-01T00:00:00Z",
    "san": ["DNS:www.example.test"],
}


def test_harborview_feed_dedupes_logs_and_precerts():
    batch = ct_feed.parse(fixture_text("ct/harborview-bank-2026-11-04.jsonl"))
    certs = _by_cn(batch)

    assert batch.source_kind == "ct_feed"
    assert batch.source_name == "ct feed"
    assert batch.observed_at == datetime(2026, 11, 4, 6, 30, tzinfo=UTC)  # latest "seen"
    assert batch.warnings == []
    assert len(batch.observations) == 6  # 9 lines: one precert, one cert logged twice
    online = certs[f"online.{HVB}"]
    assert online.attributes == {
        "subject_cn": f"online.{HVB}",
        "sans": [f"online.{HVB}", f"statements.{HVB}"],
        "issuer": "Lumen Trust RSA CA 2025",
        "serial": "4be21905aa7130",
        "not_before": "2025-11-12T00:00:00Z",
        "not_after": "2026-11-14T23:59:59Z",
    }
    assert online.external_id == "argon2025h2#1834470"  # first log of the final certificate
    assert online.links == (
        ObservedLink("covers", "host", f"online.{HVB}"),
        ObservedLink("covers", "host", f"statements.{HVB}"),
    )


def test_wildcards_kept_in_sans_but_not_linked():
    wildcard = _by_cn(ct_feed.parse(fixture_text("ct/harborview-bank-2026-11-04.jsonl")))[f"*.{HVB}"]

    assert wildcard.attributes["sans"] == [f"*.{HVB}", HVB]
    assert wildcard.links == (ObservedLink("covers", "host", HVB),)


def test_fixture_expiry_mix():
    certs = _by_cn(ct_feed.parse(fixture_text("ct/harborview-bank-2026-11-04.jsonl")))

    def days_left(cn):
        return (datetime.fromisoformat(certs[cn].attributes["not_after"]) - TODAY).days

    assert 0 < days_left(f"online.{HVB}") <= 14
    assert days_left(f"vpn.{HVB}") < 0
    assert days_left(f"api.{HVB}") > 30
    assert certs[f"api.{HVB}"].attributes["sans"] == [f"api.{HVB}"]  # IP SAN dropped


def test_quillstone_feed_epoch_dates_colon_fingerprints_der_and_bad_lines():
    batch = ct_feed.parse(fixture_text("ct/quillstone-media-2026-11-04.jsonl"))
    certs = _by_cn(batch)
    qsm = "quillstone-media.example.test"

    assert set(certs) == {f"*.cdn.{qsm}", qsm, f"cms.{qsm}", f"*.preview.{qsm}", f"shop.{qsm}"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", o.value) for o in batch.observations)
    assert certs[f"*.cdn.{qsm}"].attributes["not_after"] == "2026-11-12T23:59:59Z"
    assert f"xn--caf-dma.{qsm}" in certs[qsm].attributes["sans"]
    assert batch.warnings[0] == "line 4: not valid JSON, skipped"
    assert batch.warnings[1].startswith("line 5: SAN 'bad_label-.quillstone-media.example.test' dropped")


def test_fingerprint_from_der_when_missing():
    der = b"\x30\x82\x01\x0a" + b"atlas" * 20
    cert = {k: v for k, v in CERT.items() if k != "fingerprint_sha256"}
    cert["der"] = base64.b64encode(der).decode()
    batch = ct_feed.parse(_line(cert) + "\n" + _line(CERT | {"fingerprint_sha256": "", "der": "!!"}))

    assert [o.value for o in batch.observations] == [hashlib.sha256(der).hexdigest()]
    assert batch.warnings == ["line 2: der is not valid base64, skipped"]


def test_lone_precert_is_kept_and_label_falls_back_to_first_san():
    batch = ct_feed.parse(json.dumps({"type": "precert", "cert": CERT | {"subject": {}}}))

    assert batch.observations[0].label == "www.example.test"
    assert batch.observed_at == TODAY  # no "seen"


@pytest.mark.parametrize(
    ("cert", "warning"),
    [
        (CERT | {"fingerprint_sha256": "abc"}, "bad sha256 fingerprint"),
        (CERT | {"not_after": "next year"}, "bad validity dates"),
        ({k: v for k, v in CERT.items() if k != "not_before"}, "bad validity dates"),
    ],
)
def test_unreadable_certificates_are_skipped(cert, warning):
    batch = ct_feed.parse(_line(cert))

    assert batch.observations == []
    assert warning in batch.warnings[0]


def test_empty_feed_is_valid_but_garbage_is_not():
    assert ct_feed.parse("\n\n").observations == []
    with pytest.raises(ImportFormatError):
        ct_feed.parse("$ORIGIN example.test.\n@ IN A 192.0.2.1\n")
