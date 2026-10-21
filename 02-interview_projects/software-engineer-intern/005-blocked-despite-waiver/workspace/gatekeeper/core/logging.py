"""JSON logging with redaction.

Use ``get_logger(__name__)`` and pass structured fields with ``extra=``::

    log.info("waiver.approved", extra={"waiver_id": 7, "team_id": 3})

The message is an event name, not prose. Everything that reaches a handler
goes through ``redact``: API keys (``gk_demo_...``), bearer values, callback
secrets (``DEMO-whsec-...``) and any field whose name looks secret are masked,
so a key pasted into a payload, an error message or an exception never lands
in the logs.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

MASK = "[REDACTED]"
_SECRET_FIELD = re.compile(r"(authorization|api_?key|secret|token|password|signature)", re.I)
_SECRET_TEXT = re.compile(
    r"gk_(?:demo|live)_[A-Za-z0-9]+"
    r"|DEMO-whsec-[A-Za-z0-9-]+"
    r"|(?<=Bearer )[^\s\"',]+",
    re.I,
)
# Attributes every LogRecord has; anything else came in through ``extra=``.
_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}


def redact_text(value: str) -> str:
    return _SECRET_TEXT.sub(MASK, value)


def redact(value: Any, key: str = "") -> Any:
    if key and _SECRET_FIELD.search(key) and value not in (None, ""):
        return MASK
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in vars(record).items() if k not in _STANDARD}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service,
            "msg": record.getMessage(),
        }
        entry.update(_extras(record))
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(redact(entry), default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = f"{record.levelname:<7} {record.name}: {record.getMessage()}"
        extras = _extras(record)
        if extras:
            line += " " + " ".join(f"{k}={v}" for k, v in redact(extras).items())
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return redact_text(line)


def configure_logging(level: str, fmt: str, service: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service) if fmt == "json" else TextFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("sqlalchemy.engine", "werkzeug"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
