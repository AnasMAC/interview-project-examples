import hashlib
import json
import unittest
from dataclasses import replace

from ledger.core import db
from ledger.core import repo as rows
from ledger.core.errors import Conflict, InvalidInput, ParseError
from ledger.core.models import IngestResult, Location, Status
from ledger.dedupe.ingest import baseline_path, ingest_report
from tests.dedupe.fakes import DedupeTestCase
from tests.helpers import raw_finding

COMMIT = "4be1f0c9d2a77e1b35c0d8e6f9a1b2c3d4e5f607"
FIXTURE_KEY = raw_finding(rule_id="BRK-SECRET-004", location=Location.code("tests/fixtures/keys.py", 3), cwe=798)


class IngestReportTest(DedupeTestCase):
    def setUp(self):
        super().setUp()
        self.settings = replace(self.settings, samples_dir=self.tmp / "samples")
        self.report = self.parsers.add(b"report-1", "brackish", raw_finding(), FIXTURE_KEY)
        self.clean = self.parsers.add(b"report-2", "brackish")

    def ingest(self, data, *, branch="main", commit=COMMIT, source="brackish.sarif"):
        with db.transaction(self.conn):
            return ingest_report(self.conn, self.settings, repo=self.repo, branch=branch, commit_sha=commit,
                                 data=data, source=source)

    def count(self, table):
        return rows.fetch_one(self.conn, f"SELECT COUNT(*) AS n FROM {table}")["n"]

    def write_baseline(self, text):
        path = baseline_path(self.settings, self.repo)
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")

    def test_ingest_writes_run_findings_and_occurrences(self):
        self.write_baseline(json.dumps({"version": 1, "suppressions": [
            {"rule": "BRK-SECRET-004", "path": "tests/fixtures/**", "reason": "Dummy keys"}]}))
        result = self.ingest(self.report, commit=COMMIT.upper())
        self.assertEqual(result, IngestResult(run_id=result.run_id, repo="checkout-api", branch="main", tool="brackish",
                                              raw_count=2, new_count=2, suppressed_count=1))
        run = rows.get_run(self.conn, result.run_id)
        self.assertEqual((run.commit_sha, run.tool, run.source_name), (COMMIT, "brackish", "brackish.sarif"))
        self.assertEqual(run.source_sha256, hashlib.sha256(b"report-1").hexdigest())
        self.assertEqual((run.raw_count, run.new_count), (2, 2))
        self.assertEqual([(f.rule_id, f.suppressed) for f in self.findings()],
                         [("BRK-SQLI-001", False), ("BRK-SECRET-004", True)])
        self.assertEqual(self.count("occurrences"), 2)

    def test_clean_run_fixes_previous_findings(self):
        self.ingest(self.report)
        result = self.ingest(self.clean, commit="5c2e8a1")
        self.assertEqual((result.raw_count, result.fixed_count), (0, 2))
        self.assertEqual({f.status for f in self.findings()}, {Status.FIXED})

    def test_invalid_input_writes_nothing(self):
        for branch, commit in (("", COMMIT), ("  ", COMMIT), ("main", "4be1f0"), ("main", COMMIT + "a"),
                               ("main", "release-1"), ("main", "")):
            with self.subTest(branch=branch, commit=commit):
                with self.assertRaises(InvalidInput):
                    self.ingest(self.report, branch=branch, commit=commit)
        self.assertEqual(self.count("runs"), 0)

    def test_parse_error_writes_nothing(self):
        with self.assertRaises(ParseError) as caught:
            self.ingest(b"<html>", source="upload.bin")
        self.assertEqual(caught.exception.details["source"], "upload.bin")
        self.assertEqual(self.count("runs"), 0)

    def test_broken_baseline_writes_nothing(self):
        self.write_baseline('{"version": 1, "suppressions": [{"tool": "brackish", "reason": "all of it"}]}')
        with self.assertRaises(ParseError):
            self.ingest(self.report)
        self.assertEqual((self.count("runs"), self.count("findings")), (0, 0))

    def test_same_file_twice_is_a_conflict(self):
        first = self.ingest(self.report)
        with self.assertRaises(Conflict) as caught:
            self.ingest(self.report, source="renamed.sarif")
        self.assertEqual(caught.exception.details["run_id"], first.run_id)
        self.assertEqual(self.count("runs"), 1)
        # Same bytes on another commit or branch is a new run.
        self.assertEqual(self.ingest(self.report, commit="5c2e8a1").unchanged_count, 2)
        self.assertEqual(self.ingest(self.report, branch="release/2026.10").new_count, 2)

    def test_does_not_commit(self):
        self.conn.execute("BEGIN")
        ingest_report(self.conn, self.settings, repo=self.repo, branch="main", commit_sha=COMMIT, data=self.report,
                      source="brackish.sarif")
        self.conn.execute("ROLLBACK")
        self.assertEqual((self.count("runs"), self.count("findings")), (0, 0))


if __name__ == "__main__":
    unittest.main()
