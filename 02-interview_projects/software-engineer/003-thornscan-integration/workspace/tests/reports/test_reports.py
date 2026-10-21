import csv
import io
from datetime import date, datetime, timedelta

from ledger.core import clock, repo
from ledger.core.models import Location, Severity, Status
from ledger.reports.csv_export import export_findings_csv
from ledger.reports.html import render_html
from ledger.reports.markdown import render_markdown
from ledger.reports.weekly import build_weekly
from ledger.sla.calendar import load_calendar
from tests.helpers import TODAY, LedgerTestCase, make_finding, make_repo, make_run, make_team

MONDAY_LOCAL_0030 = datetime(2026, 9, 20, 22, 30, tzinfo=clock.UTC)  # Mon 2026-09-21 00:30 in Leipzig


class WeeklyReportTest(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.payments = make_team(self.conn, "payments", name="Payments & Billing")
        checkout = make_repo(self.conn, "checkout-api", team=self.payments)
        old_run = make_run(self.conn, checkout, ingested_at=TODAY - timedelta(days=30))
        run = make_run(self.conn, checkout)
        self.new = make_finding(self.conn, run, severity=Severity.HIGH, message="Ref <script>alert(1)</script> | x")
        # Accepted risk still breaches its SLA (sla.breach docstring, REQ-0058).
        self.old = make_finding(self.conn, old_run, triage="accepted_risk", due_at=TODAY - timedelta(days=2))
        fixed = make_finding(self.conn, old_run, status="fixed", fixed_at=TODAY - timedelta(days=1))
        repo.add_event(self.conn, fixed.id, "fixed", run_id=run.id)
        reopened = make_finding(self.conn, old_run, status="reopened")
        late_sunday = make_finding(self.conn, old_run, status="fixed")
        with clock.frozen(MONDAY_LOCAL_0030) as at:
            repo.add_event(self.conn, reopened.id, "reopened")
            at.advance(hours=-1)
            repo.add_event(self.conn, late_sunday.id, "fixed")  # Sunday 23:30 local: previous week
        make_finding(self.conn, run, suppressed=True, due_at=TODAY - timedelta(days=5))  # overdue but hidden
        make_finding(self.conn, run, triage="false_positive", status="fixed")
        self.other = make_finding(self.conn, make_run(self.conn, make_repo(self.conn, "eta-service")))
        self.calendar = load_calendar(self.settings.holidays_path, self.settings.timezone)

    def build(self, **kwargs):
        return build_weekly(self.conn, week_start=date(2026, 9, 23), calendar=self.calendar, **kwargs)

    def test_counts_one_local_week_and_skips_hidden_findings(self):
        report = self.build()
        self.assertEqual((report.week_start, report.week_end), (date(2026, 9, 21), date(2026, 9, 27)))
        self.assertEqual(len(report.teams), 2)
        week = report.teams[0]
        self.assertEqual((week.opened, week.fixed, week.reopened), (1, 1, 1))
        self.assertEqual(week.open_by_severity[Severity.MEDIUM], 2)  # old + reopened; suppressed one is hidden
        self.assertEqual(week.open_total, 3)
        self.assertEqual([f.id for f in week.oldest_open][-1], self.new.id)
        (breach,) = week.breaches
        self.assertEqual((breach.finding_id, breach.severity, breach.overdue_days), (self.old.id, Severity.MEDIUM, 2))
        self.assertEqual(report.generated_at, TODAY)

    def test_single_team(self):
        report = self.build(team_id=self.other.team_id)
        self.assertEqual([tw.team.id for tw in report.teams], [self.other.team_id])
        self.assertEqual(report.teams[0].open_total, 1)

    def test_markdown_keeps_scanner_text_inside_cells(self):
        text = render_markdown(self.build())
        self.assertIn("| Payments & Billing | 1 | 1 | 1 | 3 | 0 | 1 | 1 |", text)
        self.assertIn("Ref &lt;script&gt;alert(1)&lt;/script&gt; \\| x", text)
        self.assertIn(f"| #{self.old.id} | checkout-api | medium | 2026-09-21 | 2 |", text)

    def test_html_escapes_every_value(self):
        page = render_html(self.build())
        self.assertNotIn("<script>", page)
        self.assertIn("Ref &lt;script&gt;alert(1)&lt;/script&gt; | x", page)
        self.assertIn("<h2>Payments &amp; Billing</h2>", page)
        self.assertIn("accepted risk", page)


class CsvExportTest(LedgerTestCase):
    def test_guards_formulas_and_filters(self):
        team = make_team(self.conn, "routing")
        run = make_run(self.conn, make_repo(self.conn, "route-planner", team=team))
        formula = make_finding(self.conn, run, message='=HYPERLINK("https://evil.example.test")', cwe=79)
        make_finding(self.conn, run, status="fixed", location=Location.endpoint("https://eta.example.test/a", "q"))
        make_finding(self.conn, run, suppressed=True)
        make_finding(self.conn, make_run(self.conn))

        out = io.StringIO()
        self.assertEqual(export_findings_csv(self.conn, out, team_id=team.id), 2)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(rows[0]["id"], str(formula.id))
        self.assertEqual(rows[0]["message"], "'=HYPERLINK(\"https://evil.example.test\")")
        self.assertEqual((rows[0]["repo"], rows[0]["team"], rows[0]["cwe"]), ("route-planner", "routing", "79"))
        self.assertEqual(rows[1]["location"], "https://eta.example.test/a [q]")

        out = io.StringIO()
        self.assertEqual(export_findings_csv(self.conn, out, statuses=[Status.FIXED]), 1)
