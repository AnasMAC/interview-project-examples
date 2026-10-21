"""Small helpers shared by the parsers: decoding, JSON loading, sniffing heads, CWE fields."""

from __future__ import annotations

import json
import re
from typing import Any

from ledger.core.errors import ParseError

SNIFF_BYTES = 4096

_CWE = re.compile(r"\bcwe[-_/ ]?(\d{1,5})\b", re.IGNORECASE)


def head(data: bytes, size: int = SNIFF_BYTES) -> str:
    """The first ``size`` bytes as text for sniffing, BOM and leading whitespace removed; never raises."""
    return data[:size].decode("utf-8-sig", errors="replace").lstrip()


def decode(data: bytes, *, source: str) -> str:
    """UTF-8 text (an optional BOM is dropped); ParseError with the line of the first bad byte."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        line = data.count(b"\n", 0, exc.start) + 1
        raise ParseError(f"{source}: not UTF-8 text", source=source, line=line) from exc


def load_json(data: bytes, *, source: str) -> Any:
    try:
        return json.loads(decode(data, source=source))
    except json.JSONDecodeError as exc:
        raise ParseError(f"{source}: invalid JSON ({exc.msg})", source=source, line=exc.lineno) from exc


def obj(value: Any) -> dict[str, Any]:
    """``value`` when it is a JSON object, else ``{}``: optional nested objects are read leniently."""
    return value if isinstance(value, dict) else {}


def items(value: Any, what: str, *, source: str) -> list[Any]:
    """A JSON array that the format requires to be an array when present; absent means empty."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ParseError(f"{source}: {what} must be an array", source=source)
    return value


def optional_int(value: Any, what: str, *, source: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ParseError(f"{source}: {what} must be an integer", source=source)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ParseError(f"{source}: {what} must be an integer, got {value!r}", source=source) from None


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def cwe_from(value: Any) -> int | None:
    """CWE number from ``89``, ``"89"``, ``"CWE-89"`` or a tag like ``"external/cwe/cwe-89"``; else None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if text.isdigit():
        return int(text) or None
    match = _CWE.search(text)
    return int(match.group(1)) if match else None
