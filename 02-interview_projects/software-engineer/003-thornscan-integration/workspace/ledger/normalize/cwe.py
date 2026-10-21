"""CWE identifiers as integers."""

from __future__ import annotations

import re

_CWE = re.compile(r"^\s*(?:cwe[\s_:-]*)?0*(\d+)\b", re.IGNORECASE)


def parse_cwe(value: str | int | None) -> int | None:
    """``"CWE-89"``, ``"cwe_89"``, ``"CWE-89: SQL Injection"``, ``"89"`` and ``89`` -> 89; anything else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = _CWE.match(value)
    if match is None:
        return None
    number = int(match.group(1))
    return number if number > 0 else None
