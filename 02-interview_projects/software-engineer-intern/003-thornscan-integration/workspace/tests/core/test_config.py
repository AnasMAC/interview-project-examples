import tempfile
import unittest
from pathlib import Path

from ledger.core.config import DEFAULT_CONFIG, ROOT, load_settings
from ledger.core.errors import ConfigError


class LoadSettingsTest(unittest.TestCase):
    def test_checked_in_config(self):
        settings = load_settings(DEFAULT_CONFIG, env={})
        self.assertEqual(settings.db_path, ROOT / "var" / "ledger.db")
        self.assertEqual((settings.api_host, settings.api_port), ("127.0.0.1", 8765))
        self.assertEqual({t.role for t in settings.tokens}, {"read", "admin"})
        self.assertIsNone(settings.now)
        self.assertNotIn("DEMO-ldg", repr(settings))

    def test_environment_overrides(self):
        env = {
            "LEDGER_DB": "var/other.db",
            "LEDGER_PORT": "9123",
            "LEDGER_ADMIN_TOKEN": "DEMO-ldg-admin-0000aaaa1111bbbb",
            "LEDGER_NOW": "2026-09-23T14:00:00+02:00",
        }
        settings = load_settings(DEFAULT_CONFIG, env=env)
        self.assertEqual(settings.db_path, ROOT / "var" / "other.db")
        self.assertEqual(settings.api_port, 9123)
        admins = [t for t in settings.tokens if t.role == "admin"]
        self.assertEqual([(t.name, t.token) for t in admins], [("env-admin", "DEMO-ldg-admin-0000aaaa1111bbbb")])
        self.assertEqual(settings.now.isoformat(), "2026-09-23T12:00:00+00:00")

    def test_invalid_values(self):
        for env in ({"LEDGER_PORT": "0"}, {"LEDGER_PORT": "http"}, {"LEDGER_LOG_FORMAT": "xml"},
                    {"LEDGER_TIMEZONE": "Mars/Olympus"}, {"LEDGER_READ_TOKEN": "short"}, {"LEDGER_NOW": "2026-09-23"}):
            with self.subTest(env=env), self.assertRaises(ConfigError):
                load_settings(DEFAULT_CONFIG, env=env)

    def test_file_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "ledger.toml"
            broken.write_text('[[api.tokens]]\nname = "x"\nrole = "owner"\ntoken = "DEMO-ldg-ro-1234567890abcdef"\n')
            with self.assertRaisesRegex(ConfigError, "role"):
                load_settings(broken, env={})
            broken.write_text("[api\n")
            with self.assertRaisesRegex(ConfigError, "invalid TOML"):
                load_settings(broken, env={})
            with self.assertRaisesRegex(ConfigError, "not found"):
                load_settings(Path(tmp) / "missing.toml", env={})
