import unittest
from datetime import timedelta

from ledger.core import clock
from ledger.core.config import ROOT
from ledger.core.models import Severity, Status, Triage
from ledger.sla.breach import Breach, find_breaches
from ledger.sla.calendar import load_calendar
from tests.helpers import TODAY, LedgerTestCase, make_finding, make_repo, make_run, make_team

CALENDAR = load_calendar(ROOT / "config/holidays.toml", "Europe/Berlin")


class FindBreachesTest(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.payments = make_team(self.conn, "payments")
        self.routing = make_team(self.conn, "routing")
        self.run = make_run(self.conn, make_repo(self.conn, "checkout-api", team=self.payments))
        routing_run = make_run(self.conn, make_repo(self.conn, "route-planner", team=self.routing))
        self.overdue = self.finding(due_at=clock.parse_iso("2026-09-18T21:59:59Z"), severity=Severity.CRITICAL)
        self.oldest = self.finding(routing_run, due_at=clock.parse_iso("2026-09-14T21:59:59Z"), status=Status.REOPENED)
        self.accepted = self.finding(due_at=clock.parse_iso("2026-09-22T21:59:59Z"), triage=Triage.ACCEPTED_RISK)
        # Not breaches: due later, no SLA, fixed, suppressed, false positive.
        self.finding(due_at=TODAY + timedelta(hours=1))
        self.finding(due_at=None, severity=Severity.INFO)
        self.finding(due_at=TODAY - timedelta(days=9), status=Status.FIXED, fixed_at=TODAY)
        self.finding(due_at=TODAY - timedelta(days=9), suppressed=True, suppression_reason="test fixture")
        self.finding(due_at=TODAY - timedelta(days=9), triage=Triage.FALSE_POSITIVE)

    def finding(self, run=None, **fields):
        return make_finding(self.conn, run or self.run, **fields)

    def test_open_breaches_oldest_due_first(self):
        breaches = find_breaches(self.conn, now=TODAY, calendar=CALENDAR)
        self.assertEqual([b.finding_id for b in breaches], [self.oldest.id, self.overdue.id, self.accepted.id])
        self.assertEqual(
            breaches[1],
            Breach(self.overdue.id, self.overdue.repo_id, self.payments.id, Severity.CRITICAL,
                   clock.parse_iso("2026-09-18T21:59:59Z"), 3),  # due Fri; Mon, Tue, Wed passed
        )
        self.assertEqual([b.overdue_days for b in breaches], [7, 3, 1])

    def test_accepted_risk_still_counts(self):
        breaches = find_breaches(self.conn, now=TODAY, calendar=CALENDAR, team_id=self.payments.id)
        self.assertIn(self.accepted.id, [b.finding_id for b in breaches])

    def test_team_filter(self):
        breaches = find_breaches(self.conn, now=TODAY, calendar=CALENDAR, team_id=self.routing.id)
        self.assertEqual([(b.finding_id, b.team_id) for b in breaches], [(self.oldest.id, self.routing.id)])

    def test_due_second_is_still_in_time(self):
        due = clock.parse_iso("2026-09-18T21:59:59Z")
        ids = [b.finding_id for b in find_breaches(self.conn, now=due, calendar=CALENDAR)]
        self.assertEqual(ids, [self.oldest.id])
        ids = [b.finding_id for b in find_breaches(self.conn, now=due + timedelta(seconds=1), calendar=CALENDAR)]
        self.assertEqual(ids, [self.oldest.id, self.overdue.id])


if __name__ == "__main__":
    unittest.main()
