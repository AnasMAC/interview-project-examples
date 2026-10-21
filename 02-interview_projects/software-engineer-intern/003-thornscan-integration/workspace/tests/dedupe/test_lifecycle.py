import json
import unittest
from datetime import timedelta

from ledger.core import repo as rows
from ledger.core.models import Location, Severity, Status, Triage
from ledger.dedupe.baseline import load_baseline
from tests.dedupe.fakes import DedupeTestCase
from tests.helpers import TODAY, make_team, raw_finding

SQLI = raw_finding()  # brackish, high, src/payments/refunds.py:42, CWE-89
XSS = raw_finding(rule_id="BRK-XSS-014", location=Location.code("src/web/receipt.py", 7), cwe=79, severity="warning")


class LifecycleTest(DedupeTestCase):
    def test_new_finding(self):
        result = self.scan("brackish", SQLI)
        finding = self.only()
        self.assertEqual((finding.status, finding.severity, finding.tool_severity),
                         (Status.NEW, Severity.HIGH, "error"))
        self.assertEqual((finding.first_seen_at, finding.due_at), (TODAY, TODAY + timedelta(days=10)))
        self.assertEqual((finding.team_id, finding.first_run_id, finding.last_run_id),
                         (self.team.id, result.run_id, result.run_id))
        self.assertEqual((finding.issue_key, finding.cwe, finding.triage),
                         ("src/payments/refunds.py:42:CWE-89", 89, Triage.UNTRIAGED))
        self.assertEqual(self.events(finding.id), ["new"])
        occurrence = rows.fetch_one(self.conn, "SELECT * FROM occurrences WHERE finding_id = ?", [finding.id])
        self.assertEqual(occurrence["raw_location"], "src/payments/refunds.py:42:9")
        self.assertEqual((result.raw_count, result.new_count, result.unchanged_count, result.fixed_count), (1, 1, 0, 0))
        run = rows.get_run(self.conn, result.run_id)
        self.assertEqual((run.raw_count, run.new_count), (1, 1))

    def test_seen_again_becomes_open_and_refreshes(self):
        self.scan("brackish", SQLI)
        self.clock.advance(days=2)
        result = self.scan("brackish", SQLI)
        finding = self.only()
        self.assertEqual(finding.status, Status.OPEN)
        self.assertEqual((finding.first_seen_at, finding.last_seen_at), (TODAY, TODAY + timedelta(days=2)))
        self.assertEqual(finding.last_run_id, result.run_id)
        self.assertEqual(finding.due_at, TODAY + timedelta(days=10))  # SLA clock not restarted
        self.assertEqual((result.new_count, result.unchanged_count), (0, 1))
        self.assertEqual(self.events(finding.id), ["new"])

    def test_not_seen_by_own_tool_is_fixed(self):
        self.scan("brackish", SQLI, XSS)
        last_seen = self.scan("brackish", SQLI, XSS)  # new -> open
        self.clock.advance(days=1)
        result = self.scan("brackish", XSS)
        sqli, xss = self.findings()
        self.assertEqual((sqli.status, sqli.fixed_at), (Status.FIXED, TODAY + timedelta(days=1)))
        self.assertEqual(sqli.last_run_id, last_seen.run_id)  # the last run that saw it
        self.assertEqual(xss.status, Status.OPEN)
        self.assertEqual(result.fixed_count, 1)
        self.assertEqual(rows.get_run(self.conn, result.run_id).fixed_count, 1)
        event = rows.finding_events(self.conn, sqli.id)[-1]
        self.assertEqual((event.kind, event.from_value, event.to_value, event.run_id),
                         ("fixed", "open", "fixed", result.run_id))

    def test_new_finding_not_seen_is_fixed(self):
        self.scan("brackish", SQLI)
        self.scan("brackish")
        finding = self.only()
        self.assertEqual(finding.status, Status.FIXED)
        self.assertEqual(rows.finding_events(self.conn, finding.id)[-1].from_value, "new")

    def test_other_tool_never_fixes(self):
        self.scan("brackish", SQLI)
        for tool in ("thistle", "kitewatch", "depwarden", "pentest"):
            self.assertEqual(self.scan(tool).fixed_count, 0)
        self.assertEqual(self.only().status, Status.NEW)

    def test_fixed_then_seen_is_reopened_with_new_due_date(self):
        self.scan("brackish", SQLI)
        self.scan("brackish")
        self.clock.advance(days=20)
        result = self.scan("brackish", SQLI)
        finding = self.only()
        reopened_at = TODAY + timedelta(days=20)
        self.assertEqual((finding.status, finding.fixed_at), (Status.REOPENED, None))
        self.assertEqual((finding.due_at, finding.first_seen_at), (reopened_at + timedelta(days=10), TODAY))
        self.assertEqual((result.reopened_count, result.new_count), (1, 0))
        self.assertEqual(rows.get_run(self.conn, result.run_id).reopened_count, 1)
        self.assertEqual(self.events(finding.id), ["new", "fixed", "reopened"])

    def test_reopened_stays_reopened_then_fixes_again(self):
        self.scan("brackish", SQLI)
        self.scan("brackish")
        self.scan("brackish", SQLI)
        self.scan("brackish", SQLI)
        self.assertEqual(self.only().status, Status.REOPENED)
        self.scan("brackish")
        self.assertEqual(self.only().status, Status.FIXED)
        self.assertEqual(self.events(self.only().id), ["new", "fixed", "reopened", "fixed"])

    def test_fixed_not_seen_is_unchanged(self):
        self.scan("brackish", SQLI)
        self.scan("brackish")
        fixed = self.only()
        self.clock.advance(days=3)
        self.assertEqual(self.scan("brackish").fixed_count, 0)
        self.assertEqual(self.only(), fixed)
        self.assertEqual(self.events(fixed.id), ["new", "fixed"])

    def test_branches_are_independent(self):
        self.scan("brackish", SQLI)
        self.scan("brackish", branch="feature/refund-limits")
        self.assertEqual(self.only().status, Status.NEW)
        self.scan("brackish", SQLI, branch="feature/refund-limits")
        self.scan("brackish", branch="feature/refund-limits")
        self.assertEqual(self.only("feature/refund-limits").status, Status.FIXED)
        self.assertEqual(self.only().status, Status.NEW)
        self.assertEqual(self.only().fingerprint, self.only("feature/refund-limits").fingerprint)

    def test_triage_is_never_touched(self):
        self.scan("brackish", SQLI)
        triage = {"triage": Triage.ACCEPTED_RISK, "triage_note": "WAF rule SEC-311", "triaged_by": "appsec-admin",
                  "triaged_at": TODAY}
        rows.update(self.conn, "findings", self.only().id, triage)
        self.scan("brackish")
        self.scan("brackish", SQLI)
        finding = self.only()
        self.assertEqual(finding.status, Status.REOPENED)
        self.assertEqual((finding.triage, finding.triage_note, finding.triaged_by, finding.triaged_at),
                         (Triage.ACCEPTED_RISK, "WAF rule SEC-311", "appsec-admin", TODAY))

    def test_duplicate_sightings_in_one_run(self):
        result = self.scan("brackish", SQLI, SQLI)
        finding = self.only()
        self.assertEqual(self.occurrence_tools(finding.id), ["brackish", "brackish"])
        self.assertEqual((result.raw_count, result.new_count), (2, 1))
        result = self.scan("brackish", SQLI, SQLI)
        self.assertEqual((result.unchanged_count, self.only().status), (1, Status.OPEN))

    def test_ci_workspace_prefix_matches_relative_path(self):
        self.scan("brackish", SQLI)
        moved = raw_finding(location=Location.code("/builds/billing/checkout-api/src/payments/refunds.py", 42, 9))
        windows = raw_finding(location=Location.code("C:\\ci\\work\\checkout-api\\src\\payments\\refunds.py", 42))
        self.assertEqual(self.scan("brackish", moved).unchanged_count, 1)
        self.assertEqual(self.scan("brackish", windows).unchanged_count, 1)
        self.assertEqual(self.only().status, Status.OPEN)
        raw = rows.fetch_all(self.conn, "SELECT raw_location FROM occurrences ORDER BY id")
        self.assertEqual(raw[1]["raw_location"], "/builds/billing/checkout-api/src/payments/refunds.py:42:9")

    def test_line_drift_is_fixed_plus_new(self):
        self.scan("brackish", SQLI)
        result = self.scan("brackish", raw_finding(location=Location.code("src/payments/refunds.py", 44, 9)))
        self.assertEqual((result.new_count, result.fixed_count), (1, 1))

    def test_team_from_owners(self):
        routing = make_team(self.conn, "routing")
        self.scan("brackish", SQLI, XSS, owners={"src/web/": routing.id})
        sqli, xss = self.findings()
        self.assertEqual((sqli.team_id, xss.team_id), (self.team.id, routing.id))

    def test_info_has_no_due_date(self):
        self.scan("brackish", raw_finding(severity="note", rule_id="BRK-LOG-002"), raw_finding(severity="none"))
        self.assertEqual([f.due_at for f in self.findings()], [TODAY + timedelta(days=60), None])


class MergeTest(DedupeTestCase):
    THISTLE_SQLI = raw_finding(tool="thistle", rule_id="py.sqli.string-concat", severity="warning",
                               location=Location.code("./src/payments/refunds.py", 42, 17), message="Tainted SQL")

    def test_second_tool_merges_into_first(self):
        self.scan("brackish", SQLI)
        result = self.scan("thistle", self.THISTLE_SQLI)
        finding = self.only()
        self.assertEqual((finding.tool, finding.rule_id, finding.severity), ("brackish", "BRK-SQLI-001", Severity.HIGH))
        self.assertEqual(finding.status, Status.OPEN)
        self.assertEqual(finding.last_run_id, result.run_id)
        self.assertEqual((result.merged_count, result.new_count, result.unchanged_count), (1, 0, 1))
        self.assertEqual(self.occurrence_tools(finding.id), ["brackish", "thistle"])
        event = rows.finding_events(self.conn, finding.id)[-1]
        self.assertEqual((event.kind, event.from_value, event.to_value),
                         ("merged", "thistle:py.sqli.string-concat", "src/payments/refunds.py:42:CWE-89"))
        self.scan("thistle", self.THISTLE_SQLI)
        self.assertEqual(self.events(finding.id), ["new", "merged"])  # one merged event per tool
        self.assertEqual(self.occurrence_tools(finding.id), ["brackish", "thistle", "thistle"])

    def test_merge_works_in_both_directions(self):
        self.scan("thistle", self.THISTLE_SQLI)
        self.assertEqual(self.scan("brackish", SQLI).merged_count, 1)
        self.assertEqual(self.only().tool, "thistle")

    def test_only_own_tool_fixes_merged_finding(self):
        self.scan("brackish", SQLI)
        self.scan("thistle", self.THISTLE_SQLI)
        self.assertEqual(self.scan("thistle").fixed_count, 0)
        self.assertEqual(self.only().status, Status.OPEN)
        self.scan("brackish")
        self.assertEqual(self.only().status, Status.FIXED)
        # Thistle still reports it, so the issue is not gone.
        self.assertEqual(self.scan("thistle", self.THISTLE_SQLI).reopened_count, 1)
        self.assertEqual(self.events(self.only().id), ["new", "merged", "fixed", "reopened"])

    def test_different_cwe_on_same_line_does_not_merge(self):
        self.scan("brackish", SQLI)
        secret = raw_finding(tool="thistle", rule_id="py.secrets.hardcoded", severity="warning", cwe=798)
        self.assertEqual(self.scan("thistle", secret).merged_count, 0)
        self.assertEqual([f.tool for f in self.findings()], ["brackish", "thistle"])

    def test_no_merge_without_cwe_or_line(self):
        self.scan("brackish", SQLI)
        self.scan("thistle", raw_finding(tool="thistle", rule_id="py.sqli", cwe=None))
        no_line = Location.code("src/payments/refunds.py")
        self.scan("thistle", raw_finding(tool="thistle", rule_id="py.sqli.file", location=no_line))
        self.assertEqual([f.issue_key for f in self.findings()], ["src/payments/refunds.py:42:CWE-89", None, None])

    def test_same_tool_never_merges_with_itself(self):
        self.scan("brackish", SQLI, raw_finding(rule_id="BRK-SQLI-007"))
        self.assertEqual(len(self.findings()), 2)
        self.assertEqual(self.scan("thistle", self.THISTLE_SQLI).merged_count, 1)
        self.assertEqual(self.occurrence_tools(self.findings()[0].id), ["brackish", "thistle"])  # oldest wins

    def test_merge_is_per_branch(self):
        self.scan("brackish", SQLI)
        self.scan("thistle", self.THISTLE_SQLI, branch="release/2026.10")
        self.assertEqual(self.only("release/2026.10").tool, "thistle")

    def test_dast_findings_have_no_issue_key(self):
        url = Location.endpoint("https://checkout.fernwick.example.test/api/refunds", "order_id")
        self.scan("kitewatch", raw_finding(tool="kitewatch", rule_id="KW-SQLI", severity="High", location=url))
        self.assertIsNone(self.only().issue_key)


class SuppressionTest(DedupeTestCase):
    def baseline(self, **fields):
        path = self.tmp / ".ledger-baseline.json"
        path.write_text(json.dumps({"version": 1, "suppressions": [{"reason": "Fixture data", **fields}]}))
        return load_baseline(path)

    def test_new_finding_suppressed(self):
        result = self.scan("brackish", SQLI, XSS, baseline=self.baseline(rule="BRK-XSS-014"))
        sqli, xss = self.findings()
        self.assertEqual((sqli.suppressed, xss.suppressed, xss.suppression_reason), (False, True, "Fixture data"))
        self.assertEqual(self.events(xss.id), ["new", "suppressed"])
        self.assertEqual((result.suppressed_count, xss.status), (1, Status.NEW))

    def test_suppression_follows_the_baseline(self):
        self.scan("brackish", SQLI)
        expiring = self.baseline(path="src/payments/**", expires="2026-09-24")
        result = self.scan("brackish", SQLI, baseline=expiring)
        self.assertEqual((self.only().suppressed, result.suppressed_count), (True, 1))
        self.clock.advance(days=1)
        self.assertTrue(self.scan("brackish", SQLI, baseline=expiring).suppressed_count)  # last valid day
        self.clock.advance(days=1)
        result = self.scan("brackish", SQLI, baseline=expiring)
        finding = self.only()
        self.assertEqual((finding.suppressed, finding.suppression_reason, result.suppressed_count), (False, None, 0))
        self.assertEqual(self.events(finding.id), ["new", "suppressed", "unsuppressed"])

    def test_suppressed_findings_still_get_fixed(self):
        baseline = self.baseline(rule="BRK-SQLI-001")
        self.scan("brackish", SQLI, baseline=baseline)
        self.assertEqual(self.scan("brackish", baseline=baseline).fixed_count, 1)

    def test_merged_sighting_keeps_suppression(self):
        self.scan("brackish", SQLI, baseline=self.baseline(tool="brackish", rule="BRK-SQLI-001"))
        result = self.scan("thistle", MergeTest.THISTLE_SQLI)
        self.assertEqual((self.only().suppressed, result.suppressed_count, result.merged_count), (True, 1, 1))


if __name__ == "__main__":
    unittest.main()
