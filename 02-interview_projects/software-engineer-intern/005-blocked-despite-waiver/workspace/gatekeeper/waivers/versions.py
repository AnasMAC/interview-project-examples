"""Release versions and waiver version ranges (docs/architecture.md, "Waivers").

Versions compare as dot-separated integers, missing parts count as 0
(``4.12`` == ``4.12.0``), and a pre-release suffix sorts before its release
(``4.13.0-rc.1`` < ``4.13.0``). A leading ``v`` and ``+build`` metadata are
ignored. A range is comma-separated clauses that must all hold, e.g.
``>=4.10.0,<4.13.0``.
"""

from __future__ import annotations

import operator
import re
from collections.abc import Callable

_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
_CLAUSE = re.compile(r"^(>=|<=|==|>|<)\s*(\S+)$")
_OPERATORS: dict[str, Callable[[object, object], bool]] = {
    ">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt, "==": operator.eq,
}

VersionKey = tuple[tuple[int, ...], int, tuple[tuple[int, int | str], ...]]


def parse_version(raw: str) -> VersionKey:
    """Sort key of ``raw``; raises ValueError for anything that is not a version."""
    match = _VERSION.match(raw.strip())
    if match is None:
        raise ValueError(f"not a version: {raw!r}")
    release = [int(part) for part in match.group(1).split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    if match.group(2) is None:
        return tuple(release), 1, ()
    pre = tuple((0, int(p)) if p.isdigit() else (1, p) for p in match.group(2).split("."))
    return tuple(release), 0, pre


def parse_range(raw: str) -> list[tuple[str, VersionKey]]:
    """``[(operator, version key), ...]``; raises ValueError on a malformed range."""
    clauses = []
    for part in raw.split(","):
        match = _CLAUSE.match(part.strip())
        if match is None:
            raise ValueError(f"invalid version range clause: {part.strip()!r}")
        clauses.append((match.group(1), parse_version(match.group(2))))
    return clauses


def in_range(version: str, version_range: str) -> bool:
    """True when ``version`` satisfies every clause; an unparsable version never does."""
    try:
        key = parse_version(version)
    except ValueError:
        return False
    return all(_OPERATORS[op](key, bound) for op, bound in parse_range(version_range))
