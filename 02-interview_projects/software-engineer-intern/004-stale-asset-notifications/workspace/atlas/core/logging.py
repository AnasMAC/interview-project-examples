"""Structured logging with secret redaction.

Log an event name plus ``extra`` fields::

    logger = get_logger(__name__)
    logger.info("import.completed", extra={"org": org.slug, "job_id": job.id})

Both formatters mask API keys, webhook secrets, bearer values and
``key=value`` secrets in the message, and any extra field whose name looks
like a secret.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from atlas.core import clock

REDACTED = "[REDACTED]"
_PATTERNS = [
    (re.compile(r"atl_DEMO_[A-Za-z0-9]+"), REDACTED),
    (re.compile(r"DEMO-whsec-[A-Za-z0-9-]+"), REDACTED),
    (re.compile(r"(?i)\b(bearer\s+)\S+"), rf"\1{REDACTED}"),
    (re.compile(r"(?i)\b(secret|password|token|api_key)=[^\s&,;]+"), rf"\1={REDACTED}"),
]
_SECRET_FIELD = re.compile(r"(?i)secret|password|token|authorization|api_key")
_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(key: str, value: Any) -> Any:
    if _SECRET_FIELD.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact(value)
    return value


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": clock.isoformat(datetime.fromtimestamp(record.created, UTC)),
            "level": record.levelname,
            "logger": record.name,
            "event": redact(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact_value(key, value)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)
