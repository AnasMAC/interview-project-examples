"""JSON logging with secret redaction.

Every log line is one JSON object on stderr. Redaction runs over the rendered
message and over structured fields, so a token, a ``DEMO-`` value, an
``Authorization`` header or a password field cannot reach the log even when a
caller passes a whole request or a database row by mistake (docs/security-notes.md
"Logging" is the checklist this module implements).

Fields the formatter always emits: ``ts``, ``level``, ``logger`` and ``event``
(the message). Extra keyword arguments to ``logger.info(..., extra={"key": v})``
are appended; keys that look like secrets are replaced with ``[REDACTED]``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "csrf_token",
        "password",
        "password_hash",
        "salt",
        "secret",
        "secret_key",
        "session",
        "token",
        "token_hash",
        "access_token",
        "refresh_token",
        "api_key",
        "api_token",
        "webhook_secret",
    }
)

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer abc / authorization=abc
    (re.compile(r"(?i)\bauthorization\b\s*[:=]\s*[^\s,;]+"), "authorization: " + REDACTED),
    # Bare schemes with a credential after them
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{4,}"), r"\1 " + REDACTED),
    # Session cookie values
    (re.compile(r"bellpost_session=[^;,\s]+"), "bellpost_session=" + REDACTED),
    # Any committed demo credential, whatever its shape
    (re.compile(r"DEMO-[\w.+-]*"), REDACTED),
    # key=value pairs for anything secret-looking
    (
        re.compile(
            r"(?i)\b(password|passwd|secret|token|api[_-]?key|csrf_token)\b\s*[:=]\s*"
            r"(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1=" + REDACTED,
    ),
)

_JSON_EMPTY = json.dumps({})


def redact_text(text: str) -> str:
    """Replace secrets in a log message or free-text value."""
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any, *, key: str | None = None) -> Any:
    """Recursively redact a structured value (mapping, sequence or scalar)."""
    if key is not None and key.lower() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Redact a header mapping before it is logged."""
    return {str(name): str(redact_value(value, key=str(name))) for name, value in headers.items()}


class JsonFormatter(logging.Formatter):
    """Render log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_text(record.getMessage()),
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["traceback"] = redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact_text(record.stack_info)
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return json.dumps({**payload, "event": "[unserializable log record]"}, default=str)


class _Handler(logging.StreamHandler):
    """StreamHandler that marks itself as owned by Bellpost."""

    bellpost_owned = True


_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    """Fields a caller passed through ``extra=`` (already redacted)."""
    fields: dict[str, Any] = {}
    for name, value in record.__dict__.items():
        if name in _RESERVED or name.startswith("_"):
            continue
        fields[name] = redact_value(value, key=name)
    return fields


def configure_logging(level: str | None = None) -> None:
    """Configure the root logger once; safe to call repeatedly."""
    settings = get_settings()
    resolved = (level or settings.log_level or "INFO").upper()
    root = logging.getLogger()
    root.setLevel(resolved)
    for handler in list(root.handlers):
        if getattr(handler, "bellpost_owned", False):
            root.removeHandler(handler)
    handler = _Handler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (thin wrapper, keeps the import list short)."""
    return logging.getLogger(name)
