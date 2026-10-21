from __future__ import annotations

import json
import unittest
from typing import Any

from ledger.core.errors import ParseError
from ledger.core.models import Location
from ledger.parsers.sarif import PARSER, column_shift

SQLI_RULE = {
    "id": "BRK-SQLI-001",
    "name": "sql-from-request",
    "shortDescription": {"text": "SQL query built from request data"},
    "defaultConfiguration": {"level": "error"},
    "properties": {"tags": ["security", "external/cwe/cwe-89"], "security-severity": "8.8"},
}


def result(uri: str = "src/payments/refunds.py", region: dict[str, Any] | None = None, **fields: Any) -> dict:
    region = {"startLine": 42, "startColumn": 9} if region is None else region
    physical = {"artifactLocation": {"uri": uri, "uriBaseId": "%SRCROOT%"}, "region": region}
    return {"ruleId": "BRK-SQLI-001", "message": {"text": "order_id reaches execute()"},
            "locations": [{"physicalLocation": physical}], **fields}


def sarif(results: list[dict], *, name: str = "Brackish", version: str = "3.12.0", rules: list | None = None,
          **run_fields: Any) -> bytes:
    driver = {"name": name, "semanticVersion": version, "rules": [SQLI_RULE] if rules is None else rules}
    run = {"tool": {"driver": driver}, "results": results, **run_fields}
    return json.dumps({"version": "2.1.0", "runs": [run]}).encode()


def parse(data: bytes):
    return PARSER.parse(data, source="test.sarif")


class SarifTest(unittest.TestCase):
    def test_brackish_result(self) -> None:
        snippet = {"startLine": 42, "startColumn": 9, "endLine": 43, "snippet": {"text": "cursor.execute(q)"}}
        report = parse(sarif([result(region=snippet, partialFingerprints={"primaryLocationLineHash": "ab12:1"})]))
        self.assertEqual((report.format, report.tool, report.tool_version), ("sarif", "brackish", "3.12.0"))
        (finding,) = report.findings
        self.assertEqual(finding.location, Location.code("src/payments/refunds.py", 42, 9))
        self.assertEqual(finding.severity, "error")  # from the rule's defaultConfiguration
        self.assertEqual(finding.cwe, 89)
        self.assertEqual(finding.evidence, "cursor.execute(q)")
        self.assertEqual(finding.tool_fingerprint, "primaryLocationLineHash=ab12:1")
        self.assertEqual(finding.extra["end_line"], "43")
        self.assertEqual(finding.extra["security_severity"], "8.8")

    def test_level_precedence(self) -> None:
        rules = [{"id": "BRK-SQLI-001"}]
        findings = parse(sarif([result(level="note"), result()], rules=rules)).findings
        self.assertEqual([f.severity for f in findings], ["note", "warning"])  # SARIF default is warning

    def test_missing_region_keeps_the_file(self) -> None:
        (finding,) = parse(sarif([result(region={})])).findings
        self.assertEqual(finding.location, Location.code("src/payments/refunds.py"))

    def test_result_without_physical_location_is_skipped(self) -> None:
        bare = {"ruleId": "BRK-SQLI-001", "message": {"text": "x"},
                "locations": [{"logicalLocations": [{"fullyQualifiedName": "refunds.lookup"}]}]}
        with self.assertLogs("ledger.parsers.sarif", "WARNING"):
            self.assertEqual(parse(sarif([bare])).findings, ())

    def test_thistle_before_5_has_zero_based_columns(self) -> None:
        uri = "file:///builds/payments/checkout-api/src/payments/refunds.py"
        old = parse(sarif([result(uri, {"startLine": 42, "startColumn": 8})], name="Thistle", version="4.8.2"))
        new = parse(sarif([result(uri, {"startLine": 42, "startColumn": 9})], name="Thistle", version="5.0.1"))
        self.assertEqual(old.findings[0].location, Location.code(uri, 42, 9))  # path kept as written
        self.assertEqual(new.findings[0].location, old.findings[0].location)
        self.assertEqual((column_shift("thistle", None), column_shift("brackish", "1.0")), (1, 0))

    def test_uri_base_ids_are_resolved(self) -> None:
        bases = {"WORKSPACE": {"uri": "file:///C:/builds/routing/route-planner/"}}
        item = result("planner/cache.py")
        item["locations"][0]["physicalLocation"]["artifactLocation"]["uriBaseId"] = "WORKSPACE"
        (finding,) = parse(sarif([item], originalUriBaseIds=bases)).findings
        self.assertEqual(finding.location.path, "file:///C:/builds/routing/route-planner/planner/cache.py")
        # %SRCROOT% without a uri leaves the relative path alone
        self.assertEqual(parse(sarif([result()])).findings[0].location.path, "src/payments/refunds.py")

    def test_message_strings_and_arguments(self) -> None:
        rule = {"id": "BRK-SECRET-004", "messageStrings": {"default": {"text": "Credential in {0} ({1}, {2})"}},
                "properties": {"tags": ["security", "external/cwe/cwe-798"]}}
        item = result(ruleId="BRK-SECRET-004", message={"id": "default", "arguments": ["PSP_API_KEY", "live"]})
        (finding,) = parse(sarif([item], rules=[rule])).findings
        self.assertEqual(finding.message, "Credential in PSP_API_KEY (live, {2})")
        self.assertEqual(finding.cwe, 798)

    def test_rule_by_index_and_cwe_property(self) -> None:
        rules = [{"id": "TH-INJ-SQL", "properties": {"cwe": "CWE-89"}}]
        item = result(ruleIndex=0, message={})
        del item["ruleId"]
        (finding,) = parse(sarif([item], name="Thistle", rules=rules)).findings
        self.assertEqual((finding.rule_id, finding.cwe, finding.message), ("TH-INJ-SQL", 89, "TH-INJ-SQL"))

    def test_no_cwe_unless_stated(self) -> None:
        rules = [{"id": "BRK-SQLI-001", "properties": {"tags": ["security"]}}]
        self.assertIsNone(parse(sarif([result()], rules=rules)).findings[0].cwe)

    def test_pass_and_suppressed_results_are_not_findings(self) -> None:
        results = [result(kind="pass"), result(suppressions=[{"kind": "inSource"}]),
                   result(suppressions=[{"kind": "external", "status": "rejected"}])]
        self.assertEqual(len(parse(sarif(results)).findings), 1)

    def test_clean_run_still_names_the_tool(self) -> None:
        report = parse(sarif([], name="Thistle", version="4.8.2"))
        self.assertEqual((report.tool, report.findings), ("thistle", ()))

    def test_one_tool_per_file(self) -> None:
        runs = [{"tool": {"driver": {"name": n}}, "results": []} for n in ("Brackish", "Thistle")]
        with self.assertRaisesRegex(ParseError, "two tools"):
            parse(json.dumps({"version": "2.1.0", "runs": runs}).encode())
        same = [{"tool": {"driver": {"name": "Brackish"}}, "results": [result()]}] * 2
        self.assertEqual(len(parse(json.dumps({"version": "2.1.0", "runs": same}).encode()).findings), 2)

    def test_malformed_logs(self) -> None:
        cases = [b"{", b"[]", b'{"runs": []}', b'{"runs": [{"tool": {}}]}', sarif([{"message": {"text": "x"}}])]
        for data in cases:
            with self.subTest(data=data[:40]), self.assertRaises(ParseError):
                parse(data)
        with self.assertRaises(ParseError) as ctx:
            parse(b'{\n"runs": [\n  {,}\n]}')
        self.assertEqual(ctx.exception.details["line"], 3)


if __name__ == "__main__":
    unittest.main()
