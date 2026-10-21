"""Settings: ``config/ledger.toml`` first, then ``LEDGER_*`` environment overrides.

Relative paths (in the file or the environment) are resolved against the
project root, the directory that holds ``pyproject.toml``. Library code takes a
``Settings`` argument; only entry points call ``get_settings()``.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ledger.core import clock
from ledger.core.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "ledger.toml"
ROLES = ("read", "admin")
LOG_FORMATS = ("text", "json")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass(frozen=True)
class ApiToken:
    name: str
    role: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    root: Path
    db_path: Path
    busy_timeout_ms: int
    api_host: str
    api_port: int
    max_upload_bytes: int
    tokens: tuple[ApiToken, ...]
    log_level: str
    log_format: str
    timezone: str
    now: datetime | None
    samples_dir: Path
    sla_policy_path: Path
    holidays_path: Path


def load_settings(path: Path | str | None = None, env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    config_path = Path(path or env.get("LEDGER_CONFIG") or DEFAULT_CONFIG)
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {config_path}: {exc}") from exc

    database, api = data.get("database", {}), data.get("api", {})
    logging_, paths, ledger = data.get("logging", {}), data.get("paths", {}), data.get("ledger", {})
    tokens = [_token(item) for item in api.get("tokens", [])]
    for role in ROLES:
        value = env.get(f"LEDGER_{role.upper()}_TOKEN")
        if value:
            tokens = [token for token in tokens if token.role != role] + [_token({"name": f"env-{role}", "role": role, "token": value})]

    log_level = str(env.get("LEDGER_LOG_LEVEL") or logging_.get("level", "INFO")).upper()
    log_format = str(env.get("LEDGER_LOG_FORMAT") or logging_.get("format", "text"))
    if log_level not in LOG_LEVELS:
        raise ConfigError(f"log level must be one of {', '.join(LOG_LEVELS)}, got {log_level!r}")
    if log_format not in LOG_FORMATS:
        raise ConfigError(f"log format must be one of {', '.join(LOG_FORMATS)}, got {log_format!r}")
    timezone = str(env.get("LEDGER_TIMEZONE") or ledger.get("timezone", "Europe/Berlin"))
    clock.zone(timezone)

    return Settings(
        root=ROOT,
        db_path=_path(env.get("LEDGER_DB") or database.get("path", "var/ledger.db")),
        busy_timeout_ms=_int(database.get("busy_timeout_ms", 5000), "database.busy_timeout_ms", 0, 600_000),
        api_host=str(env.get("LEDGER_HOST") or api.get("host", "127.0.0.1")),
        api_port=_int(env.get("LEDGER_PORT") or api.get("port", 8765), "LEDGER_PORT", 1, 65535),
        max_upload_bytes=_int(api.get("max_upload_bytes", 10 * 1024 * 1024), "api.max_upload_bytes", 1, 1 << 30),
        tokens=tuple(tokens),
        log_level=log_level,
        log_format=log_format,
        timezone=timezone,
        now=_instant(env.get("LEDGER_NOW") or ledger.get("now")),
        samples_dir=_path(paths.get("samples", "samples")),
        sla_policy_path=_path(paths.get("sla_policy", "config/sla.toml")),
        holidays_path=_path(paths.get("holidays", "config/holidays.toml")),
    )


_current: Settings | None = None


def get_settings() -> Settings:
    global _current
    if _current is None:
        _current = load_settings()
    return _current


def set_settings(settings: Settings | None) -> None:
    global _current
    _current = settings


def _token(item: Mapping[str, Any]) -> ApiToken:
    name, role, token = (str(item.get(key, "")) for key in ("name", "role", "token"))
    if role not in ROLES:
        raise ConfigError(f"token {name!r}: role must be one of {', '.join(ROLES)}")
    if len(token) < 16:
        raise ConfigError(f"token {name!r}: must be at least 16 characters")
    return ApiToken(name=name or f"unnamed-{role}", role=role, token=token)


def _path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _int(value: Any, name: str, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc
    if not low <= number <= high:
        raise ConfigError(f"{name} must be between {low} and {high}, got {number}")
    return number


def _instant(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        value = value.isoformat()
    try:
        return clock.parse_iso(str(value))
    except ValueError as exc:
        raise ConfigError(f"LEDGER_NOW / ledger.now: {exc}") from exc
