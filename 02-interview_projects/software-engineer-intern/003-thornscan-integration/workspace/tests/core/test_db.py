import threading
import unittest

from ledger.core import db
from tests.helpers import LedgerTestCase, make_team


class TransactionTest(LedgerTestCase):
    def count(self):
        return self.conn.execute("SELECT count(*) FROM teams").fetchone()[0]

    def test_pragmas(self):
        self.assertEqual(self.conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)

    def test_commit_and_rollback(self):
        with db.transaction(self.conn):
            make_team(self.conn, "payments")
        with self.assertRaises(RuntimeError), db.transaction(self.conn):
            make_team(self.conn, "routing")
            raise RuntimeError("boom")
        self.assertEqual(self.count(), 1)
        self.assertFalse(self.conn.in_transaction)

    def test_nested_transaction_is_a_savepoint(self):
        with db.transaction(self.conn):
            make_team(self.conn, "payments")
            with self.assertRaises(RuntimeError), db.transaction(self.conn):
                make_team(self.conn, "routing")
                raise RuntimeError("inner")
            make_team(self.conn, "fleet")
        slugs = [row[0] for row in self.conn.execute("SELECT slug FROM teams ORDER BY id")]
        self.assertEqual(slugs, ["payments", "fleet"])

    def test_concurrent_writers_wait_for_the_lock(self):
        errors = []

        def writer(prefix):
            conn = db.open_db(self.settings)
            try:
                for i in range(25):
                    with db.transaction(conn):
                        make_team(conn, f"{prefix}-{i}")
            except Exception as exc:  # surfaced below
                errors.append(exc)
            finally:
                conn.close()

        threads = [threading.Thread(target=writer, args=(name,)) for name in ("a", "b", "c")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(self.count(), 75)

    def test_memory_database(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
