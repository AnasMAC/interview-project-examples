from __future__ import annotations

import json
import logging

from gatekeeper.core.logging import MASK, JsonFormatter, TextFormatter, redact, redact_text

KEY = "gk_demo_4f8a1c2d9e7b6a5f0c3d2e1b4a7f9c8d"


def _record(msg: str, **extra) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "gatekeeper.test", "levelname": "INFO",
                                    "levelno": logging.INFO, "msg": msg})
    record.__dict__.update(extra)
    return record


def test_redact_text_masks_keys_bearer_values_and_callback_secrets():
    text = (f"key {KEY} header Bearer abc.def-123, secret DEMO-whsec-payments-api-9f1c2b3a4d5e "
            "and nothing else")

    assert redact_text(text) == (f"key {MASK} header Bearer {MASK}, secret {MASK} "
                                 "and nothing else")


def test_redact_walks_nested_values_and_secret_looking_fields():
    value = {"headers": {"Authorization": "Bearer x", "X-Request-Id": "r1"},
             "callback_secret": "anything", "api_key": "", "items": [KEY, 3],
             "service": "payments-api"}

    assert redact(value) == {"headers": {"Authorization": MASK, "X-Request-Id": "r1"},
                             "callback_secret": MASK, "api_key": "", "items": [MASK, 3],
                             "service": "payments-api"}


def test_json_formatter_emits_one_redacted_object():
    record = _record(f"auth.rejected key={KEY}", team_id=4, payload={"token": "t0k"})

    line = JsonFormatter("app").format(record)

    entry = json.loads(line)
    assert entry["msg"] == f"auth.rejected key={MASK}"
    assert entry["team_id"] == 4 and entry["payload"] == {"token": MASK}
    assert entry["service"] == "app" and entry["level"] == "INFO"
    assert KEY not in line


def test_text_formatter_redacts_extras_and_message():
    line = TextFormatter().format(_record(f"issued {KEY}", key_hash="abc", team_id=2))

    assert KEY not in line and "team_id=2" in line and "abc" in line
