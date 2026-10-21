"""End to end: seed, ingest the demo manifest, then read it back through the CLI, the API and a weekly report.

Nothing is faked: real parsers, normalization, dedupe, OWNERS, baselines, SLA calendar, CLI and HTTP server, on
a temporary database. Each sample file is ingested at 06:00 UTC on the day in its name (pentest reports, named
by month only, on the day of the entry before them), in manifest order.
"""

from __future__ import annotations

import contextlib
import http.client
import io
import json
import re
import threading
from datetime import date, datetime, timedelta

from ledger import cli
from ledger.api.server import make_server
from ledger.core import clock, config, db
from ledger.core import repo as rows
from ledger.dedupe.ingest import ingest_report
from ledger.reports.markdown import render_markdown
from ledger.reports.weekly import build_weekly
from ledger.seed import seed_database
from ledger.sla.calendar import load_calendar
from tests.helpers import TODAY, LedgerTestCase

ADMIN, READ = "DEMO-ldg-admin-2c8e41b7a9d05f36", "DEMO-ldg-ro-7f3a9c21e5b84d60"
# new, reopened, fixed, merged, suppressed per manifest entry, in manifest order.
OUTCOMES = [
    (6, 0, 0, 0, 1), (2, 0, 0, 3, 0), (7, 0, 0, 0, 0), (4, 0, 0, 0, 1), (4, 0, 0, 0, 0), (4, 0, 0, 0, 0),
    (1, 0, 0, 2, 0), (3, 0, 0, 0, 0), (1, 0, 1, 0, 1), (1, 0, 1, 0, 1), (7, 0, 0, 0, 1), (2, 0, 2, 0, 0),
    (0, 0, 0, 2, 0), (4, 0, 0, 0, 0), (0, 1, 1, 0, 1), (1, 0, 1, 2, 0), (1, 0, 4, 0, 0), (1, 0, 1, 0, 0),
    (0, 1, 1, 0, 0), (0, 0, 0, 0, 0),
]


class DemoPipelineTest(LedgerTestCase):
    def setUp(self):
        super().setUp()
        config.set_settings(self.settings)
        self.addCleanup(config.set_settings, None)
        with db.transaction(self.conn):
            seed_database(self.conn)
        manifest = self.settings.samples_dir / "manifest.json"
        self.results, day = [], None
        for index, run in enumerate(json.loads(manifest.read_text(encoding="utf-8"))["runs"]):
            named = re.search(r"\d{4}-\d{2}-\d{2}", run["file"])
            day = date.fromisoformat(named.group(0)) if named else day
            self.clock.set(datetime(day.year, day.month, day.day, 6, index, tzinfo=clock.UTC))
            repository = rows.repo_by_name(self.conn, run["repo"])
            with db.transaction(self.conn):
                self.results.append(ingest_report(
                    self.conn, self.settings, repo=repository, branch=run["branch"], commit_sha=run["commit"],
                    data=(manifest.parent / run["file"]).read_bytes(), source=run["file"].rsplit("/", 1)[-1]))
        self.clock.set(TODAY)

    def finding(self, repo_name, where, branch="main"):
        sql = ("SELECT f.*, t.slug AS team FROM findings f JOIN repos r ON r.id = f.repo_id"
               " JOIN teams t ON t.id = f.team_id WHERE r.name = ? AND f.branch = ?"
               " AND (f.path || ':' || f.line = ? OR f.rule_id = ?)")
        (row,) = rows.fetch_all(self.conn, sql, [repo_name, branch, where, where])
        return row

    def events(self, finding_id):
        return [event.kind for event in rows.finding_events(self.conn, finding_id)]

    def test_lifecycle_merge_baseline_owners_and_sla(self):
        got = [(r.new_count, r.reopened_count, r.fixed_count, r.merged_count, r.suppressed_count) for r in self.results]
        self.assertEqual(got, OUTCOMES)
        sqli = self.finding("checkout-api", "src/payments/refunds.py:42")
        self.assertEqual((sqli["tool"], sqli["status"], sqli["issue_key"]),
                         ("brackish", "open", "src/payments/refunds.py:42:CWE-89"))
        self.assertEqual(self.events(sqli["id"]), ["new", "merged"])
        sql = "SELECT DISTINCT tool FROM occurrences WHERE finding_id = ? ORDER BY tool"
        self.assertEqual([row["tool"] for row in rows.fetch_all(self.conn, sql, [sqli["id"]])], ["brackish", "thistle"])
        feature = self.finding("checkout-api", "src/payments/refunds.py:42", "feature/refund-limits")
        self.assertEqual(feature["status"], "new")  # own lifecycle per branch
        md5 = self.finding("checkout-api", "src/checkout/session.py:11")
        self.assertEqual((md5["status"], md5["team"]), ("reopened", "identity"))
        self.assertEqual(self.events(md5["id"]), ["new", "fixed", "reopened"])
        self.assertEqual(md5["due_at"], "2026-10-26T22:59:59Z")  # 30 business days from Mon 2026-09-14, Oct 3 off
        self.assertEqual(self.finding("route-planner", "planner/cache.py:52")["status"], "fixed")  # line moved: new 55
        self.assertEqual(self.finding("route-planner", "planner/cache.py:55")["status"], "open")
        self.assertEqual(self.finding("route-planner", "planner/api/eta_webhooks.py:88")["team"], "tracking")
        self.assertEqual(self.finding("checkout-api", "src/checkout/auth/refund_tokens.py:24")["team"], "payments")
        fixture = self.finding("checkout-api", "tests/fixtures/gateway_keys.py:15")
        self.assertEqual((fixture["suppressed"], fixture["suppression_reason"][:22]), (1, "Test card numbers and "))
        self.assertEqual(self.finding("checkout-api", "DWA-2026-0142")["suppressed"], 1)
        self.assertEqual(self.finding("route-planner", "KW-HDR-007")["suppressed"], 0)  # entry expired 2026-08-31
        kw_sqli = self.finding("checkout-api", "KW-SQLI-001")
        self.assertEqual((kw_sqli["severity"], kw_sqli["tool_severity"]), ("critical", "5"))
        self.assertEqual(kw_sqli["due_at"], "2026-08-27T21:59:59Z")  # Mon 08-24 + 3 business days, 23:59:59 Berlin

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["sla-check", "--team", "payments", "--json"]), 1)
        breached = {item["finding_id"] for item in json.loads(out.getvalue())}
        self.assertIn(kw_sqli["id"], breached)
        self.assertNotIn(fixture["id"], breached)

    def test_api_list_detail_and_triage(self):
        server = make_server(self.settings, host="127.0.0.1", port=0)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def call(method, path, token=READ, body=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            self.addCleanup(conn.close)
            conn.request(method, path, body=body and json.dumps(body), headers={"Authorization": f"Bearer {token}"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())

        status, page = call("GET", "/api/v1/findings?repo=route-planner&branch=main&status=reopened")
        self.assertEqual((status, page["total"]), (200, 1))
        self.assertEqual(page["items"][0]["location"]["path"], "planner/geo/import_gpx.py")
        merged = self.finding("route-planner", "planner/admin/export.py:71")
        status, detail = call("GET", f"/api/v1/findings/{merged['id']}")
        self.assertEqual({o["tool"] for o in detail["occurrences"]}, {"brackish", "thistle"})
        self.assertTrue(any(o["raw_location"].startswith("file:///C:/builds/") for o in detail["occurrences"]))
        triage = {"triage": "accepted_risk", "note": "SEC-330"}
        status, body = call("POST", f"/api/v1/findings/{merged['id']}/triage", ADMIN, triage)
        self.assertEqual((status, body["triage"], body["triaged_by"]), (200, "accepted_risk", "appsec-admin"))
        self.assertEqual(call("GET", f"/api/v1/findings/{merged['id']}")[1]["events"][-1]["actor"], "appsec-admin")
        status, teams = call("GET", "/api/v1/teams")
        self.assertEqual([team["slug"] for team in teams["items"]][:2], ["customs", "fleet"])

    def test_weekly_report_of_the_demo_week(self):
        calendar = load_calendar(self.settings.holidays_path, self.settings.timezone)
        payments = rows.team_by_slug(self.conn, "payments")
        report = build_weekly(self.conn, week_start=date(2026, 9, 14), calendar=calendar, team_id=payments.id)
        (week,) = report.teams
        text = render_markdown(report)
        self.assertTrue(text.startswith("# Ledger weekly report 2026-09-14 to 2026-09-20\n"))
        self.assertIn(f"| Payments | {week.opened} | {week.fixed} | {week.reopened} | {week.open_total} |", text)
        # Seed history plus the demo's 2026-09-14 runs (MD5 reopened, XSS/HSTS/cookie/HG-CHK-02 fixed).
        numbers = (week.opened, week.fixed, week.reopened, week.open_total, len(week.breaches))
        self.assertEqual(numbers, (40, 40, 2, 324, 101))
        self.assertEqual(report.generated_at - TODAY, timedelta(0))
