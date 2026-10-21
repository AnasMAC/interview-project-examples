import contextlib
import io
import json
import os
from dataclasses import replace
from datetime import datetime
from unittest import mock

from ledger import cli
from ledger.core import config, repo
from ledger.core.models import Severity, Status, Triage
from tests.helpers import LedgerTestCase, make_finding, make_repo, make_run, make_team, sarif_report

REFUNDS = ("src/payments/refunds.py", 42)
WEBHOOKS = ("src/payments/webhooks.py", 63)


class CliTestCase(LedgerTestCase):
    """The real CLI on a temporary database; ingest and reports use the real packages and samples/repos/."""

    def setUp(self):
        super().setUp()
        config.set_settings(self.settings)
        self.addCleanup(config.set_settings, None)
        self.team = make_team(self.conn, "payments")
        self.repo = make_repo(self.conn, "checkout-api", team=self.team)
        self.run = make_run(self.conn, self.repo)

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def write(self, name, data=b"{}"):
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


class GeneralTest(CliTestCase):
    def test_usage_errors_exit_2(self):
        self.assertEqual(self.cli("frobnicate")[0], 2)
        self.assertEqual(self.cli("triage", "1", "--set", "wontfix")[0], 2)
        self.assertEqual(self.cli("--version")[0], 0)

    def test_migrate_and_pending_schema(self):
        fresh = replace(self.settings, db_path=self.tmp / "fresh.db")
        config.set_settings(fresh)
        code, _, err = self.cli("findings")
        self.assertEqual(code, 2)
        self.assertIn("ledger migrate", err)
        self.assertEqual(self.cli("migrate")[:2], (0, f"applied 0001_initial\nschema version 1 ({fresh.db_path})\n"))
        self.assertEqual(self.cli("migrate")[1], f"schema version 1 ({fresh.db_path})\n")

    def test_seed_refuses_existing_data_without_reset(self):
        self.assertEqual(self.cli("seed")[0], 2)
        self.assertEqual(repo.fetch_one(self.conn, "SELECT COUNT(*) FROM findings")[0], 0)
        code, out, _ = self.cli("seed", "--reset")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("teams: 8, repos: 14, runs: 362, findings: 3000,"), out)
        self.assertEqual(repo.fetch_one(self.conn, "SELECT slug FROM teams WHERE id = 1")[0], "payments")


class IngestTest(CliTestCase):
    def runs(self):
        sql = "SELECT source_name, branch, commit_sha, tool, raw_count FROM runs WHERE id != ? ORDER BY id"
        return [tuple(row) for row in repo.fetch_all(self.conn, sql, [self.run.id])]

    def test_failed_file_does_not_undo_the_others(self):
        good = self.write("a.sarif", sarif_report(REFUNDS, WEBHOOKS))
        bad = self.write("b.sarif", b"broken")
        last = self.write("c.sarif", sarif_report(WEBHOOKS))
        args = ["--repo", "checkout-api", "--branch", "main", "--commit", "4be1f0c9d2", str(good), str(bad), str(last)]
        code, out, err = self.cli("ingest", *args)
        self.assertEqual(code, 1)
        self.assertEqual([run[0] for run in self.runs()], ["a.sarif", "c.sarif"])
        self.assertIn("2 raw, 2 new, 0 reopened, 0 fixed", out)
        self.assertIn("1 raw, 0 new, 0 reopened, 1 fixed", out)
        self.assertIn("ingested 2 of 3 file(s)", out)
        self.assertIn(f"FAIL {bad}: b.sarif: no parser recognises this content", err)
        self.assertEqual(self.cli("ingest", *args[:6], str(good))[0], 1)  # same file, same commit: conflict

    def test_manifest_in_order_relative_to_its_directory(self):
        make_repo(self.conn, "route-planner")
        self.write("samples/brackish/one.sarif", sarif_report(REFUNDS))
        kitewatch = {"kitewatch": "2.9.3", "alerts": [{"pluginId": "KW-INFO-005", "alert": "Server version disclosed",
                     "risk": 1, "instances": [{"uri": "https://route-planner.staging.fernwick.example.test/"}]}]}
        self.write("samples/kitewatch/two.json", json.dumps(kitewatch).encode())
        manifest = self.write("samples/manifest.json", json.dumps({"runs": [
            {"file": "brackish/one.sarif", "repo": "checkout-api", "branch": "main", "commit": "4be1f0c9d2"},
            {"file": "kitewatch/two.json", "repo": "route-planner", "branch": "dev", "commit": "77aa01c",
             "format": "kitewatch", "tool": "kitewatch", "note": "ignored by the CLI"},
        ]}).encode())
        code, out, _ = self.cli("ingest", "--manifest", str(manifest))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.runs(), [("one.sarif", "main", "4be1f0c9d2", "brackish", 1),
                                       ("two.json", "dev", "77aa01c", "kitewatch", 1)])

    def test_bad_invocations(self):
        self.write("a.sarif")
        manifest = self.write("m.json", b'{"runs": [{"file": "a.sarif", "repo": "checkout-api"}]}')
        self.assertEqual(self.cli("ingest", str(self.tmp / "a.sarif"))[0], 2)
        self.assertEqual(self.cli("ingest", "--repo", "nope", "--branch", "main", "--commit", "abc1234", "x")[0], 2)
        self.assertEqual(self.cli("ingest", "--manifest", str(manifest))[0], 2)
        self.assertEqual(self.cli("ingest", "--manifest", str(manifest), "--repo", "checkout-api")[0], 2)
        code, _, err = self.cli("ingest", "--repo", "checkout-api", "--branch", "main", "--commit", "abc1234",
                                str(self.tmp / "missing"))
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)
        self.assertEqual(self.runs(), [])


class QueryAndTriageTest(CliTestCase):
    def test_findings_table_and_json(self):
        high = make_finding(self.conn, self.run, severity=Severity.HIGH)
        make_finding(self.conn, self.run, severity=Severity.LOW, status=Status.FIXED)
        code, out, _ = self.cli("findings", "--team", "payments", "--severity", "high", "--severity", "critical")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("ID"))
        self.assertIn(f"{high.id}", lines[1])
        self.assertIn(high.location.display(), lines[1])
        self.assertEqual(lines[-1], "1 of 1 finding(s)")
        code, out, _ = self.cli("findings", "--status", "fixed", "--json")
        self.assertEqual((json.loads(out)["total"], json.loads(out)["items"][0]["severity"]), (1, "low"))

    def test_triage_actor_defaults_to_user(self):
        finding = make_finding(self.conn, self.run)
        with mock.patch.dict(os.environ, {"USER": "ekowalczyk"}):
            code, out, _ = self.cli("triage", str(finding.id), "--set", "false_positive", "--note", "test fixture")
        self.assertEqual((code, out), (0, f"finding {finding.id} triage=false_positive by ekowalczyk\n"))
        self.assertEqual(self.cli("triage", str(finding.id), "--set", "confirmed", "--actor", "praman")[0], 0)
        self.assertEqual(repo.get_finding(self.conn, finding.id).triage, Triage.CONFIRMED)
        self.assertEqual([e.actor for e in repo.finding_events(self.conn, finding.id)], ["ekowalczyk", "praman"])
        self.assertEqual(self.cli("triage", "999999", "--set", "confirmed")[0], 2)


class ReportAndSlaTest(CliTestCase):
    def test_report_markdown_html_and_csv(self):
        make_finding(self.conn, self.run, severity=Severity.HIGH, message="Refund amount not checked")
        code, out, _ = self.cli("report", "--week", "2026-09-21", "--team", "payments", "--format", "md")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# Ledger weekly report 2026-09-21 to 2026-09-27\n"), out)
        self.assertIn("| Payments | 1 | 0 | 0 | 1 | 0 | 1 | 0 |", out)
        out_path = self.tmp / "week.html"
        self.assertEqual(self.cli("report", "--week", "2026-09-21", "--format", "html", "--out", str(out_path))[0], 0)
        self.assertIn("<h2>Payments</h2>", out_path.read_text(encoding="utf-8"))
        code, out, err = self.cli("report", "--format", "csv", "--team", "payments")
        self.assertEqual((code, out.splitlines()[0].split(",")[:3]), (0, ["id", "repo", "branch"]))
        self.assertEqual(err, "wrote 1 row(s)\n")
        self.assertEqual(self.cli("report", "--week", "2026-09-15", "--format", "md")[0], 2)  # a Tuesday
        self.assertEqual(self.cli("report", "--format", "md")[0], 2)
        self.assertEqual(self.cli("report", "--week", "2026-09-21", "--team", "nope", "--format", "md")[0], 2)

    def test_sla_check_exit_codes(self):
        self.assertEqual(self.cli("sla-check", "--team", "payments")[:2], (0, "no SLA breaches\n"))
        due = datetime.fromisoformat("2026-09-18T21:59:59+00:00")  # Fri 23:59:59 in Leipzig
        finding = make_finding(self.conn, self.run, severity=Severity.CRITICAL, due_at=due)
        make_finding(self.conn, self.run, severity=Severity.CRITICAL, due_at=due, triage=Triage.FALSE_POSITIVE)
        code, out, _ = self.cli("sla-check")
        self.assertEqual(code, 1)
        self.assertIn(f"BREACH finding {finding.id} critical checkout-api team=payments due 2026-09-18T21:59:59Z"
                      " (3 business day(s) overdue)", out)
        self.assertIn("1 SLA breach(es)", out)
        code, out, _ = self.cli("sla-check", "--json")
        (item,) = json.loads(out)
        self.assertEqual((code, item["team"], item["severity"], item["overdue_days"]), (1, "payments", "critical", 3))
        self.assertEqual(self.cli("sla-check", "--team", "nope")[0], 2)
