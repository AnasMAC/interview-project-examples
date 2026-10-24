from __future__ import annotations
import argparse
import subprocess
import sys
import unittest

from app import top_validation, validate_row, duplicaion, import_findings


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "app.py", *arguments], capture_output=True, text=True, check=False)


class StarterTests(unittest.TestCase):
    def testCli_whenHelpRequested_returnsUsage(self) -> None:
        result = _run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--input", result.stdout)
    def testCli_whenInputMissing_reportsReadableError(self) -> None:
        result = _run_cli("--input", "inputs/does-not-exist.json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def testCli_whenJsonMalformed_reportsReadableError(self) -> None:
        result = _run_cli("--input", "inputs/malformed-input.txt")
        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    # def testCli_whenFeatureUnimplemented_returnsExplicitPlaceholder(self) -> None:
    #     result = _run_cli("--input", "inputs/primary.json")
    #     self.assertEqual(result.returncode, 3)
    #     self.assertIn("STARTER: implement", result.stderr)
    #     self.assertEqual(result.stdout, "")


class FeatureTests(unittest.TestCase):
    def setUp(self):
        # Reusable arguments and assets for the feature tests
        self.args = argparse.Namespace(tenant="north", input="dummy.json")
        self.assets = ["web-1", "db-1"]

    def test_topValidation_malformedInput(self) -> None:
        # Test that passing a bad tenant raises the ValueError you wrote
        payload = {"tenant": "south", "assets": [], "records": []}

        with self.assertRaises(ValueError) as context:
            top_validation(payload, self.args)

        self.assertIn("Tenant in JSON does not match", str(context.exception))

    def test_empty_batch_returns_zeros(self):
        payload = {
            "tenant": "north",
            "assets": self.assets,
            "records": []
        }
        result = import_findings(payload, self.args)

        self.assertEqual(result["summary"]["input_rows"], 0)
        self.assertEqual(result["summary"]["accepted_rows"], 0)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["rejected"], [])

    def test_validate_row_rejects_wrong_tenant(self):
        row = {
            "source_id": "1", "tenant": "south", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "/api", "severity": "high", "evidence": "x"
        }
        is_valid, reason = validate_row(row, "north", self.assets)

        self.assertFalse(is_valid)
        self.assertIn("Tenant does not match", reason)

    def test_validate_row_rejects_empty_string(self):
        row = {
            "source_id": "1", "tenant": "north", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "   ",  # Blank after strip
            "severity": "high", "evidence": "x"
        }
        is_valid, reason = validate_row(row, "north", self.assets)

        self.assertFalse(is_valid)
        self.assertIn("empty", reason)

    def test_duplication_merges_evidence_and_upgrades_severity(self):
        unique_findings = {}

        # 1. Insert initial finding with 'low' severity
        row1 = {
            "source_id": "src-2", "tenant": "north", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "/api", "severity": "low", "evidence": "evidence B"
        }
        duplicaion(row1, unique_findings)

        # 2. Insert duplicate finding with 'critical' severity
        row2 = {
            "source_id": "src-1", "tenant": "north", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "/api", "severity": "critical", "evidence": "evidence A"
        }
        is_duplicated = duplicaion(row2, unique_findings)
        self.assertTrue(is_duplicated)

        # 3. Verify the merged result
        dedup_key = ("north", "web-1", "rule-a", "/api")
        merged = unique_findings[dedup_key]

        self.assertEqual(merged["severity"], "critical")
        self.assertEqual(merged["evidence"], ["evidence A", "evidence B"])
        self.assertEqual(merged["source_ids"], ["src-1", "src-2"])

    def test_exact_location_identity_prevents_merging(self):
        unique_findings = {}

        row1 = {
            "source_id": "1", "tenant": "north", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "http://api.com", "severity": "low", "evidence": "x"
        }
        row2 = {
            "source_id": "2", "tenant": "north", "asset_id": "web-1",
            "rule_id": "rule-a", "location": "https://api.com", "severity": "low", "evidence": "y"
        }

        duplicaion(row1, unique_findings)
        is_duplicated = duplicaion(row2, unique_findings)

        # The locations differ by 'https', so they should NOT be considered duplicates
        self.assertFalse(is_duplicated)
        self.assertEqual(len(unique_findings), 2)

if __name__ == "__main__":
    unittest.main()
