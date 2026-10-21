import hashlib

from ledger.core import clock, db, migrations
from ledger.core.errors import Conflict
from ledger.core.models import Severity
from ledger.seed import ANCHOR, seed_database
from ledger.sla.calendar import load_calendar
from tests.helpers import LedgerTestCase

TABLES = ("teams", "repos", "runs", "findings", "occurrences", "finding_events")


class SeedTest(LedgerTestCase):
    def seed(self, conn=None, **kwargs):
        conn = conn or self.conn
        with db.transaction(conn):
            return seed_database(conn, **kwargs)  # checked-in config/sla.toml and config/holidays.toml

    def digest(self, conn):
        sha = hashlib.sha256()
        for table in TABLES:
            for row in conn.execute(f"SELECT * FROM {table} ORDER BY id"):
                sha.update(repr(tuple(row)).encode())
        return sha.hexdigest()

    def other_db(self, name):
        conn = db.connect(self.tmp / name)
        self.addCleanup(conn.close)
        migrations.migrate(conn)
        return conn

    def test_volumes_and_determinism(self):
        counts = self.seed()
        self.assertEqual((counts["teams"], counts["repos"], counts["findings"]), (8, 14, 3000))
        self.assertEqual(counts, {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES})
        self.assertGreater(counts["occurrences"], 3 * counts["findings"])
        same, other = self.other_db("same.db"), self.other_db("other.db")
        self.seed(same)
        self.seed(other, seed=7)
        self.assertEqual(self.digest(self.conn), self.digest(same))
        self.assertNotEqual(self.digest(self.conn), self.digest(other))

    def test_refuses_existing_data_unless_reset(self):
        self.seed()
        with self.assertRaises(Conflict):
            self.seed()
        self.assertEqual(self.seed(reset=True, scale=2)["findings"], 6000)

    def test_history_looks_like_ten_weeks_of_ci(self):
        self.seed()
        q = self.conn.execute
        self.assertEqual(q("SELECT full_name FROM repos WHERE id = 3").fetchone()[0], "routing/route-planner")
        for column, values in (("status", 4), ("triage", 4), ("severity", 5), ("tool", 5)):
            self.assertEqual(q(f"SELECT COUNT(DISTINCT {column}) FROM findings").fetchone()[0], values)
        latest = max(q(f"SELECT MAX({c}) FROM {t}").fetchone()[0] for t, c in (
            ("runs", "ingested_at"), ("finding_events", "created_at"), ("findings", "triaged_at")))  # fmt: skip
        self.assertLessEqual(latest, clock.isoformat(ANCHOR))
        self.assertEqual(q("SELECT COUNT(*) FROM findings f WHERE NOT EXISTS"
                           " (SELECT 1 FROM occurrences o WHERE o.finding_id = f.id)").fetchone()[0], 0)  # fmt: skip
        self.assertEqual(q("SELECT COUNT(*) FROM findings WHERE tool IN ('brackish', 'thistle')"
                           " AND issue_key IS NULL").fetchone()[0], 0)  # fmt: skip
        merged = q("SELECT finding_id FROM finding_events WHERE kind = 'merged' LIMIT 1").fetchone()[0]
        tools = q("SELECT COUNT(DISTINCT tool) FROM occurrences WHERE finding_id = ?", [merged]).fetchone()[0]
        self.assertEqual(tools, 2)

        row = q("SELECT * FROM findings WHERE severity = 'critical' AND status = 'open' LIMIT 1").fetchone()
        calendar = load_calendar(self.settings.holidays_path, self.settings.timezone)
        due = calendar.add_business_days(clock.parse_iso(row["first_seen_at"]), 3)
        self.assertEqual(row["due_at"], clock.isoformat(due))
        self.assertIsNone(q("SELECT MAX(due_at) FROM findings WHERE severity = ?", [Severity.INFO]).fetchone()[0])
