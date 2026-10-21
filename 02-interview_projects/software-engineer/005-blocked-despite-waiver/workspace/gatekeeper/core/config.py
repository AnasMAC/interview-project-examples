"""Settings read from the environment once per process.

Every knob is a ``GATE_*`` variable except ``DATABASE_URL``. Components read
``get_settings()``; tests override fields with ``dataclasses.replace`` and
``create_app(settings)`` instead of touching ``os.environ``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _dev_now(env: str) -> datetime | None:
    """``GATE_NOW``: pin ``clock.now()`` to one instant on a dev stack (see core.clock)."""
    raw = os.environ.get("GATE_NOW", "").strip()
    if not raw:
        return None
    if env == "prod":
        raise ValueError("GATE_NOW is a dev-only setting and is refused when GATE_ENV=prod")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise ValueError(f"GATE_NOW needs an offset, e.g. 2026-12-02T11:00:00Z (got {raw!r})")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    service_name: str
    log_level: str
    log_format: str  # "json" or "text"
    max_payload_bytes: int  # request bodies above this are rejected with 413
    callback_timeout_s: int
    callback_max_attempts: int
    scheduler_interval_s: int
    waiver_max_days: int  # longest waiver a team may request
    waiver_notice_hour: int  # local hour (team timezone) for expiry notices
    dev_now: datetime | None = None  # GATE_NOW: pinned "now" of a dev stack, None = wall clock


def load_settings() -> Settings:
    env = os.environ.get("GATE_ENV", "dev")
    return Settings(
        env=env,
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://gatekeeper:gatekeeper-demo@localhost:5432/gatekeeper",
        ),
        service_name=os.environ.get("GATE_SERVICE_NAME", "app"),
        log_level=os.environ.get("GATE_LOG_LEVEL", "INFO").upper(),
        log_format=os.environ.get("GATE_LOG_FORMAT", "json"),
        max_payload_bytes=_int("GATE_MAX_PAYLOAD_BYTES", 1024 * 1024),
        callback_timeout_s=_int("GATE_CALLBACK_TIMEOUT_S", 5),
        callback_max_attempts=_int("GATE_CALLBACK_MAX_ATTEMPTS", 8),
        scheduler_interval_s=_int("GATE_SCHEDULER_INTERVAL_S", 30),
        waiver_max_days=_int("GATE_WAIVER_MAX_DAYS", 90),
        waiver_notice_hour=_int("GATE_WAIVER_NOTICE_HOUR", 9),
        dev_now=_dev_now(env),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
