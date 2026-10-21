"""Application settings.

Every setting is read from the environment. ``BELLPOST_*`` is the current
prefix; the older ``HELPDESK_*`` names predate the 1.3 rename and are still
read as a fallback for the machines, scripts and archived configs that were
never updated (see ``config/.env.2019.bak``). Precedence is always
``BELLPOST_*`` first, then ``HELPDESK_*``, then the default below.

Settings are read once and cached; tests and scripts that change the
environment call :func:`reload_settings` (or use :func:`override_settings`).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ENV_PREFIX = "BELLPOST_"
LEGACY_ENV_PREFIX = "HELPDESK_"

DEFAULT_DATABASE_URL = "postgresql+psycopg://bellpost:bellpost@127.0.0.1:55432/bellpost"
DEFAULT_SECRET_KEY = "DEMO-session-secret-not-for-production"

_PATH_FIELDS = ("attachment_root", "spool_dir", "spool_processed_dir", "spool_failed_dir")


def env_value(name: str, default: str | None = None) -> str | None:
    """Return ``BELLPOST_<name>``, falling back to ``HELPDESK_<name>``."""
    for prefix in (ENV_PREFIX, LEGACY_ENV_PREFIX):
        value = os.environ.get(prefix + name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    """Resolved application settings."""

    env: str = "development"
    secret_key: str = DEFAULT_SECRET_KEY
    database_url: str = DEFAULT_DATABASE_URL
    attachment_root: Path = Path("var/attachments")
    spool_dir: Path = Path("spool/incoming")
    spool_processed_dir: Path = Path("spool/processed")
    spool_failed_dir: Path = Path("spool/failed")
    log_level: str = "INFO"
    now: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "env", self.env.strip().lower())
        object.__setattr__(self, "log_level", self.log_level.strip().upper())
        for field in _PATH_FIELDS:
            object.__setattr__(self, field, Path(getattr(self, field)))

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"

    @property
    def uses_demo_secret(self) -> bool:
        return self.secret_key.startswith("DEMO-")


def load_settings() -> Settings:
    """Build settings from the environment."""
    return Settings(
        env=env_value("ENV", "development") or "development",
        secret_key=env_value("SECRET_KEY", DEFAULT_SECRET_KEY) or DEFAULT_SECRET_KEY,
        database_url=env_value("DATABASE_URL", DEFAULT_DATABASE_URL) or DEFAULT_DATABASE_URL,
        attachment_root=Path(env_value("ATTACHMENT_ROOT", "var/attachments") or "var/attachments"),
        spool_dir=Path(env_value("SPOOL_DIR", "spool/incoming") or "spool/incoming"),
        spool_processed_dir=Path(env_value("SPOOL_PROCESSED_DIR", "spool/processed") or "spool/processed"),
        spool_failed_dir=Path(env_value("SPOOL_FAILED_DIR", "spool/failed") or "spool/failed"),
        log_level=env_value("LOG_LEVEL", "INFO") or "INFO",
        now=env_value("NOW"),
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached settings, loading them on first use."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings | None) -> None:
    """Install settings directly (used by tests and ``create_app``)."""
    global _settings
    _settings = settings


def reload_settings() -> Settings:
    """Drop the cache and read the environment again."""
    set_settings(None)
    return get_settings()


@contextmanager
def override_settings(**changes: Any) -> Iterator[Settings]:
    """Temporarily replace individual settings.

    >>> with override_settings(log_level="DEBUG"):
    ...     ...
    """
    previous = get_settings()
    current = replace(previous, **changes)
    set_settings(current)
    try:
        yield current
    finally:
        set_settings(previous)
