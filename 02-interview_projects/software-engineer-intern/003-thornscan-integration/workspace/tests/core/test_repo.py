import unittest
from datetime import timedelta

from ledger.core import repo
from ledger.core.errors import Conflict, NotFound
from ledger.core.models import Location, LocationKind, Severity, Status, Triage, as_dict
from tests.helpers import TODAY, LedgerTestCase, make_finding, make_repo, make_run, make_team


class RepoHelpersTest(LedgerTestCase):
    def test_insert_update_and_lookups(self):
        team = make_team(self.conn, "payments")
        checkout = make_repo(self.conn, "checkout-api", team=team)
        self.assertEqual(repo.team_by_slug(self.conn, "payments"), team)
        self.assertEqual(repo.repo_by_name(self.conn, "checkout-api").full_name, "payments/checkout-api")
        self.assertIsNone(repo.repo_by_name(self.conn, "nope"))
        repo.update(self.conn, "repos", checkout.id, {"full_name": "billing/checkout-api"})
        self.assertEqual(repo.get_repo(self.conn, checkout.id).full_name, "billing/checkout-api")
        with self.assertRaises(Conflict):
            make_team(self.conn, "payments")
        with self.assertRaises(NotFound):
            repo.get_team(self.conn, 999)
        with self.assertRaises(NotFound):
            repo.update(self.conn, "teams", 999, {"name": "x"})
        with self.assertRaises(ValueError):
            repo.fetch_all(self.conn, f"SELECT * FROM teams WHERE id IN ({repo.placeholders([])})")

    def test_finding_round_trip(self):
        run = make_run(self.conn, tool="depwarden")
        finding = make_finding(
            self.conn, run, location=Location.dependency("harbor-json", "2.3.1"), severity=Severity.HIGH,
            suppressed=True, triage=Triage.ACCEPTED_RISK, triaged_at=TODAY,
        )
        self.assertEqual(finding.location.kind, LocationKind.PACKAGE)
        self.assertEqual(finding.location.display(), "harbor-json@2.3.1")
        self.assertEqual((finding.status, finding.severity, finding.suppressed), (Status.NEW, Severity.HIGH, True))
        self.assertTrue(finding.is_open)
        self.assertEqual(finding.due_at, TODAY + timedelta(days=42))
        data = as_dict(finding)
        self.assertEqual((data["first_seen_at"], data["triage"]), ("2026-09-23T12:00:00Z", "accepted_risk"))
        self.assertEqual(data["location"]["package"], "harbor-json")

    def test_events_in_order(self):
        finding = make_finding(self.conn)
        repo.add_event(self.conn, finding.id, "new", run_id=finding.first_run_id, to_value="new")
        self.clock.advance(days=1)
        repo.add_event(self.conn, finding.id, "triage", from_value="untriaged", to_value="confirmed", actor="appsec-admin")
        events = repo.finding_events(self.conn, finding.id)
        self.assertEqual([e.kind for e in events], ["new", "triage"])
        self.assertEqual(events[1].created_at, TODAY + timedelta(days=1))
        self.assertEqual(events[1].actor, "appsec-admin")

    def test_location_display(self):
        self.assertEqual(Location.code("src/app.py", 12, 4).display(), "src/app.py:12:4")
        self.assertEqual(Location.code("src/app.py").display(), "src/app.py")
        url = "https://checkout.fernwick.example.test/api/refunds"
        self.assertEqual(Location.endpoint(url, "id").display(), f"{url} [id]")
        self.assertEqual(Location.dependency("harbor-json").display(), "harbor-json")
        self.assertEqual([s.rank for s in Severity], [4, 3, 2, 1, 0])


if __name__ == "__main__":
    unittest.main()
