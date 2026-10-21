"""Which hosts a certificate covers.

Certificate wildcards follow RFC 6125: ``*`` stands for exactly one whole
left-most label, so ``*.a.test`` covers ``x.a.test`` but neither ``a.test``
nor ``y.x.a.test``. (Ownership rules use ``fnmatch`` instead, where ``*``
crosses dots; the two are deliberately different.)
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import Q

from atlas.core.normalize import NormalizationError, normalize_hostname


def hostname_matches(pattern: str, hostname: str) -> bool:
    try:
        pattern = normalize_hostname(pattern, allow_wildcard=True)
        hostname = normalize_hostname(hostname)
    except NormalizationError:
        return False
    if not pattern.startswith("*."):
        return pattern == hostname
    first, _, rest = hostname.partition(".")
    return bool(first) and rest == pattern[2:]


def covered_names(attributes: dict) -> list[str]:
    """The SANs of a certificate, normalized; unreadable entries are ignored."""
    names: list[str] = []
    for name in attributes.get("sans") or ():
        try:
            normalized = normalize_hostname(str(name), allow_wildcard=True)
        except NormalizationError:
            continue
        if normalized not in names:
            names.append(normalized)
    return names


def candidate_hosts(names: Iterable[str]) -> Q | None:
    """A ``Q`` on ``Asset.key`` that keeps every host one of ``names`` may cover.

    It is deliberately loose (``*.a.test`` lets ``y.x.a.test`` through):
    ``hostname_matches`` makes the decision.
    """
    query = None
    for name in names:
        part = Q(key__endswith=name[1:]) if name.startswith("*.") else Q(key=name)
        query = part if query is None else query | part
    return query


def candidate_sans(hostname: str) -> list[str]:
    """SAN values that could cover ``hostname``: itself and its one-label wildcard."""
    names = [hostname]
    _, dot, parent = hostname.partition(".")
    if dot and "." in parent:
        names.append(f"*.{parent}")
    return names
