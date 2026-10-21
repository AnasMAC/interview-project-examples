import io
import json
import logging
import unittest

from ledger.core import log


class LogTest(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.addCleanup(lambda: logging.getLogger("ledger").handlers.clear())

    def test_json_lines_carry_extras_and_redact_tokens(self):
        log.configure("DEBUG", "json", self.stream)
        log.get_logger("api.auth").warning(
            "auth.rejected", extra={"header": "Bearer DEMO-ldg-ro-7f3a9c21e5b84d60", "status": 401}
        )
        line = json.loads(self.stream.getvalue())
        self.assertEqual((line["logger"], line["event"], line["level"]), ("ledger.api.auth", "auth.rejected", "warning"))
        self.assertEqual(line["status"], 401)
        self.assertEqual(line["header"], "Bearer [REDACTED]")
        self.assertTrue(line["ts"].endswith("Z"))

    def test_text_format_and_level(self):
        log.configure("INFO", "text", self.stream)
        logger = log.get_logger("ledger.cli")
        logger.debug("hidden")
        logger.info("ingest.done %s", "checkout-api", extra={"token": "ldg-admin-2c8e41b7a9d05f36"})
        output = self.stream.getvalue()
        self.assertNotIn("hidden", output)
        self.assertIn("INFO    ledger.cli ingest.done checkout-api token=[REDACTED]", output)
