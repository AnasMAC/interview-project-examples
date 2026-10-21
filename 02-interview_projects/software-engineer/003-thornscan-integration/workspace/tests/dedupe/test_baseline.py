import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from ledger.core import clock
from ledger.core.config import ROOT
from ledger.core.errors import ParseError
from ledger.core.models import Location
from ledger.dedupe.baseline import Baseline, glob_to_regex, load_baseline
from ledger.dedupe.fingerprint import fingerprint
from tests.dedupe.test_keys import norm
from tests.helpers import TODAY


class BaselineTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / ".ledger-baseline.json"
        self.enterContext(clock.frozen(TODAY))

    def load(self, *entries, version=1):
        self.path.write_text(json.dumps({"version": version, "suppressions": list(entries)}), encoding="utf-8")
        return load_baseline(self.path)

    def test_missing_file_is_empty(self):
        self.assertEqual(load_baseline(self.path), Baseline())
        self.assertIsNone(Baseline().match(norm()))

    def test_entry_fields(self):
        baseline = self.load({"tool": "brackish", "rule": "BRK-SQLI-001", "path": "src/**", "reason": "Reviewed",
                              "expires": "2026-12-31", "ticket": "SEC-214", "added_by": "mrojas"})
        (entry,) = baseline.entries
        self.assertEqual((entry.expires, entry.ticket, entry.added_by), (date(2026, 12, 31), "SEC-214", "mrojas"))
        self.assertIs(baseline.match(norm()), entry)

    def test_every_criterion_must_match(self):
        baseline = self.load({"tool": "thistle", "rule": "BRK-SQLI-001", "reason": "x"})
        self.assertIsNone(baseline.match(norm()))
        self.assertIsNotNone(baseline.match(norm(tool="thistle")))
        self.assertIsNone(self.load({"rule": "BRK-SQLI-002", "reason": "x"}).match(norm()))
        self.assertIsNone(self.load({"path": "src/web/**", "reason": "x"}).match(norm()))

    def test_path_never_matches_non_code_findings(self):
        dast = norm(tool="kitewatch", location=Location.endpoint("https://checkout.fernwick.example.test/src/x"))
        self.assertIsNone(self.load({"path": "**", "reason": "x"}).match(dast))

    def test_fingerprint_entry(self):
        baseline = self.load({"fingerprint": fingerprint(norm()), "reason": "Accepted in SEC-290"})
        self.assertIsNotNone(baseline.match(norm(location=Location.code("./src/payments/refunds.py", 42))))
        self.assertIsNone(baseline.match(norm(location=Location.code("src/payments/refunds.py", 43))))

    def test_expiry_is_the_last_valid_day(self):
        baseline = self.load({"rule": "BRK-SQLI-001", "reason": "x", "expires": "2026-09-23"})
        self.assertIsNotNone(baseline.match(norm()))
        with clock.frozen(datetime(2026, 9, 24, 0, 0, tzinfo=clock.UTC)):
            self.assertIsNone(baseline.match(norm()))

    def test_first_match_wins(self):
        baseline = self.load({"path": "src/payments/", "reason": "first"}, {"rule": "BRK-SQLI-001", "reason": "second"})
        self.assertEqual(baseline.match(norm()).reason, "first")

    def test_globs(self):
        cases = [
            ("tests/fixtures/**", "tests/fixtures/cards/visa.json", True),
            ("tests/fixtures/**", "tests/fixtures.py", False),
            ("**/migrations/*.py", "src/payments/migrations/0001_init.py", True),
            ("**/migrations/*.py", "migrations/0001_init.py", True),
            ("**/migrations/*.py", "src/migrations/old/0001.py", False),
            ("vendor/", "vendor/gateway/client.py", True),
            ("/vendor/", "src/vendor/client.py", False),
            ("src/*.py", "src/app.py", True),
            ("src/*.py", "src/payments/app.py", False),
            ("src/app?.py", "src/app2.py", True),
            ("docs/[draft].md", "docs/[draft].md", True),
            ("docs/[draft].md", "docs/d.md", False),
        ]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(glob_to_regex(pattern).fullmatch(path) is not None, expected)

    def test_malformed_files(self):
        cases = {
            "not json": "{",
            "wrong version": json.dumps({"version": 2, "suppressions": []}),
            "no list": json.dumps({"version": 1, "suppressions": {}}),
            "not an object": json.dumps({"version": 1, "suppressions": ["BRK-SQLI-001"]}),
            "unknown key": json.dumps({"version": 1, "suppressions": [{"rules": "BRK-SQLI-001", "reason": "x"}]}),
            "no reason": json.dumps({"version": 1, "suppressions": [{"rule": "BRK-SQLI-001"}]}),
            "tool only": json.dumps({"version": 1, "suppressions": [{"tool": "brackish", "reason": "x"}]}),
            "empty value": json.dumps({"version": 1, "suppressions": [{"rule": " ", "reason": "x"}]}),
            "bad date": json.dumps({"version": 1, "suppressions": [{"rule": "R", "reason": "x", "expires": "31.12."}]}),
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ParseError) as caught:
                    load_baseline(self.path)
                self.assertEqual(caught.exception.details["source"], str(self.path))

    def test_sample_repo_baselines_load(self):
        for name in ("checkout-api", "route-planner"):
            with self.subTest(name):
                baseline = load_baseline(ROOT / "samples" / "repos" / name / ".ledger-baseline.json")
                self.assertTrue(baseline.entries)
                self.assertTrue(all(entry.reason and entry.ticket for entry in baseline.entries))
        checkout = load_baseline(ROOT / "samples/repos/checkout-api/.ledger-baseline.json")
        fixture = norm(rule_id="BRK-SECRET-004", location=Location.code("tests/fixtures/gateway_keys.py", 3), cwe=798)
        self.assertEqual(checkout.match(fixture).ticket, "SEC-214")
        self.assertIsNone(checkout.match(norm()))


if __name__ == "__main__":
    unittest.main()
