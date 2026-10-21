from __future__ import annotations

import json
import unittest

from ledger.core.errors import ParseError
from ledger.core.models import Location
from ledger.parsers.kitewatch import PARSER

SITE = "https://checkout-api.staging.fernwick.example.test"


def v2(*alerts: dict) -> bytes:
    return json.dumps({"kitewatch": "2.9.3", "site": SITE, "alerts": list(alerts)}).encode()


def v3(*findings: dict) -> bytes:
    return json.dumps({"schema": "https://schemas.kitewatch.example.test/report/v3.json",
                       "scanner": {"name": "Kitewatch", "version": "3.2.1"}, "findings": list(findings)}).encode()


def parse(data: bytes):
    return PARSER.parse(data, source="kitewatch.json")


SQLI_V2 = {"pluginId": "KW-SQLI-001", "alert": "SQL injection (error based)", "risk": 5, "confidence": 3,
           "cweid": "89", "instances": [
               {"uri": f"{SITE}/api/v1/refunds", "method": "POST", "param": "order_id", "evidence": "near \"'\""},
               {"uri": f"{SITE}/api/v1/orders", "method": "GET", "param": "", "evidence": ""}]}
SQLI_V3 = {"rule": "KW-SQLI-001", "title": "SQL injection (error based)", "severity": "Critical", "cwe": "CWE-89",
           "request": {"method": "POST", "url": f"{SITE}/api/v1/refunds", "parameter": "order_id"},
           "evidence": "near \"'\"", "fingerprint": "kw3:abc"}


class KitewatchTest(unittest.TestCase):
    def test_v2_one_finding_per_instance_with_numeric_risk(self) -> None:
        report = parse(v2(SQLI_V2))
        self.assertEqual((report.tool, report.tool_version), ("kitewatch", "2.9.3"))
        first, second = report.findings
        self.assertEqual(first.severity, "5")
        self.assertEqual(first.location, Location.endpoint(f"{SITE}/api/v1/refunds", "order_id"))
        self.assertEqual((first.cwe, first.evidence, first.extra["method"]), (89, "near \"'\"", "POST"))
        self.assertEqual(second.location, Location.endpoint(f"{SITE}/api/v1/orders"))  # "" parameter -> None
        self.assertIsNone(second.evidence)

    def test_v3_word_severity(self) -> None:
        report = parse(v3(SQLI_V3))
        self.assertEqual(report.tool_version, "3.2.1")
        (finding,) = report.findings
        self.assertEqual((finding.rule_id, finding.severity, finding.cwe), ("KW-SQLI-001", "Critical", 89))
        self.assertEqual(finding.tool_fingerprint, "kw3:abc")

    def test_same_issue_has_the_same_location_in_both_versions(self) -> None:
        old, new = parse(v2(SQLI_V2)).findings[0], parse(v3(SQLI_V3)).findings[0]
        self.assertEqual((old.rule_id, old.location), (new.rule_id, new.location))

    def test_v2_unknown_cwe_markers(self) -> None:
        for cweid in ("-1", "0", 0, None):
            with self.subTest(cweid=cweid):
                self.assertIsNone(parse(v2({**SQLI_V2, "cweid": cweid})).findings[0].cwe)

    def test_v2_risk_must_be_one_to_five(self) -> None:
        self.assertEqual(parse(v2({**SQLI_V2, "risk": "4"})).findings[0].severity, "4")
        for risk in (0, 6, "High", True, None):
            with self.subTest(risk=risk), self.assertRaises(ParseError):
                parse(v2({**SQLI_V2, "risk": risk}))

    def test_v3_required_fields(self) -> None:
        for field in ("rule", "severity"):
            with self.subTest(field=field), self.assertRaises(ParseError):
                parse(v3({key: value for key, value in SQLI_V3.items() if key != field}))
        with self.assertRaises(ParseError):
            parse(v3({**SQLI_V3, "request": {"method": "GET"}}))

    def test_not_a_kitewatch_document(self) -> None:
        for data in (b"[]", b'{"scanner": {"name": "Kitewatch"}}', b'{"kitewatch": "2.9", "alerts": {}}'):
            with self.subTest(data=data), self.assertRaises(ParseError):
                parse(data)

    def test_sniff(self) -> None:
        self.assertTrue(PARSER.sniff(v2(), None))
        self.assertTrue(PARSER.sniff(v3(), None))
        self.assertFalse(PARSER.sniff(b'{"schema": "https://schemas.kitewatch.example.test/report/v4.json"}', None))
        self.assertFalse(PARSER.sniff(b'{"$schema": "sarif", "runs": [{"message": "kitewatch"}]}', None))


if __name__ == "__main__":
    unittest.main()
