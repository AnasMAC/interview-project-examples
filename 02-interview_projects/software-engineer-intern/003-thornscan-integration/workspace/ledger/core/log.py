"""Logging: dotted event names, key/value extras, text or JSON lines, token redaction.

Usage::

    log = get_logger("dedupe.lifecycle")
    log.info("lifecycle.fixed", extra={"run_id": run.id, "count": 3})
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from typing import Any, TextIO

from ledger.core.clock import UTC, isoformat

_RESERVED = set(vars(logging.LogRecord("x", logging.INFO, "", 0, "", (), None))) | {"message", "asctime"}
_SECRET = re.compile(r"(?i)(bearer\s+)[^\s\"',;]+|\b(?:DEMO-)?ldg-[a-z]+-[0-9a-f]{8,}\b")


def redact(text: str) -> str:
    """Mask bearer credentials and Ledger API tokens anywhere in ``text``."""
    return _SECRET.sub(lambda match: (match.group(1) or "") + "[REDACTED]", text)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in vars(record).items() if key not in _RESERVED and not key.startswith("_")}


def _timestamp(record: logging.LogRecord) -> str:
    return isoformat(datetime.fromtimestamp(record.created, UTC))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": _timestamp(record),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
            **_extras(record),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(f"{key}={value}" for key, value in _extras(record).items())
        line = f"{_timestamp(record)} {record.levelname:<7} {record.name} {record.getMessage()}"
        if fields:
            line = f"{line} {fields}"
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return redact(line)


def configure(level: str = "INFO", fmt: str = "text", stream: TextIO | None = None) -> None:
    """Install one handler on the ``ledger`` logger. Safe to call more than once."""
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    root = logging.getLogger("ledger")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name == "ledger" or name.startswith("ledger.") else f"ledger.{name}")
