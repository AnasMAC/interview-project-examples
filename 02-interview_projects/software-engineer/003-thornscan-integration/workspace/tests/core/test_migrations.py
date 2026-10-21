import sqlite3
import tempfile
import unittest
from pathlib import Path

from ledger.core import db, migrations
from ledger.core.errors import MigrationError

TABLES = {"teams", "repos", "runs", "findings", "occurrences", "finding_events", "schema_migrations"}


class MigrationsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "migrations"
        self.dir.mkdir()
        self.conn = db.connect(Path(tmp.name) / "test.db")
        self.addCleanup(self.conn.close)

    def write(self, name, sql):
        (self.dir / name).write_text(sql, encoding="utf-8")

    def tables(self):
        return {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def test_real_migrations_apply_once(self):
        applied = migrations.migrate(self.conn)
        self.assertEqual([m.version for m in applied], [1])
        self.assertTrue(TABLES <= self.tables())
        self.assertEqual(migrations.migrate(self.conn), [])
        self.assertEqual(migrations.current_version(self.conn), 1)

    def test_numeric_order_and_target(self):
        self.write("0010_c.sql", "ALTER TABLE t ADD COLUMN c TEXT;")
        self.write("0002_b.sql", "ALTER TABLE t ADD COLUMN b TEXT;")
        self.write("0001_a.sql", "CREATE TABLE t (a TEXT);")
        self.write("README.txt", "not a migration")
        self.assertEqual([m.version for m in migrations.migrate(self.conn, self.dir, target=2)], [1, 2])
        self.assertEqual([m.name for m in migrations.pending(self.conn, self.dir)], ["c"])
        migrations.migrate(self.conn, self.dir)
        self.assertEqual([row[1] for row in self.conn.execute("PRAGMA table_info(t)")], ["a", "b", "c"])

    def test_failed_migration_leaves_nothing_behind(self):
        self.write("0001_a.sql", "CREATE TABLE t (a TEXT);")
        self.write("0002_bad.sql", "CREATE TABLE half (x TEXT);\nINSERT INTO missing VALUES (1);")
        with self.assertRaisesRegex(MigrationError, "0002_bad failed"):
            migrations.migrate(self.conn, self.dir)
        self.assertNotIn("half", self.tables())
        self.assertEqual(migrations.current_version(self.conn), 1)
        self.assertFalse(self.conn.in_transaction)

    def test_edited_migration_is_refused(self):
        self.write("0001_a.sql", "CREATE TABLE t (a TEXT);")
        migrations.migrate(self.conn, self.dir)
        self.write("0001_a.sql", "CREATE TABLE t (a TEXT, b TEXT);")
        with self.assertRaisesRegex(MigrationError, "edited"):
            migrations.migrate(self.conn, self.dir)

    def test_bad_names_and_duplicate_versions(self):
        self.write("1_initial.sql", "SELECT 1;")
        with self.assertRaisesRegex(MigrationError, "bad migration file name"):
            migrations.discover(self.dir)
        (self.dir / "1_initial.sql").unlink()
        self.write("0003_a.sql", "SELECT 1;")
        self.write("0003_b.sql", "SELECT 1;")
        with self.assertRaisesRegex(MigrationError, "share version 0003"):
            migrations.discover(self.dir)

    def test_concurrent_migrator_already_applied_it(self):
        self.write("0001_a.sql", "CREATE TABLE t (a TEXT);")
        stale = migrations.pending(self.conn, self.dir)
        migrations.migrate(self.conn, self.dir)
        self.assertFalse(migrations._apply(self.conn, stale[0]))

    def test_refuses_open_transaction(self):
        self.conn.execute("BEGIN")
        self.addCleanup(lambda: self.conn.in_transaction and self.conn.execute("ROLLBACK"))
        with self.assertRaises(MigrationError):
            migrations.migrate(self.conn, self.dir)


class SchemaTest(unittest.TestCase):
    def test_foreign_keys_enforced(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        migrations.migrate(conn)
        conn.execute("INSERT INTO teams (slug, name, email) VALUES ('payments', 'Payments', 'p@fernwick.example.test')")
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO repos (name, full_name, url, team_id) VALUES ('x', 'y/x', 'u', 99)")
