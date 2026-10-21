"""Which waiver covers a violated rule result (docs/architecture.md, "Waivers").

A waiver matches when it is approved, ``expires_at`` is after the evaluation
instant (an expired waiver the scheduler has not swept yet does not count),
it belongs to the team, its service is null or the evaluated one, its rule is
the result's canonical rule and its version range is null or contains the
release version. A release without a version only matches waivers without a
range. Of several matches the one expiring last wins (ties: lowest id).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from gatekeeper.waivers.versions import in_range

RULE_IDS = (
    "dependency.max_severity",
    "secrets.allowed",
    "sast.new_high_max",
    "tests.min_pass_rate",
    "signing.required",
)
RULE_ALIASES = {"sast.max_high": "sast.new_high_max"}


def canonical_rule(rule: str) -> str:
    return RULE_ALIASES.get(rule, rule)


def covers(
    waiver: Any, *, team_id: int, service_id: int, rule: str, version: str | None, at: datetime
) -> bool:
    if waiver.status != "approved" or waiver.expires_at <= at or waiver.team_id != team_id:
        return False
    if waiver.service_id is not None and waiver.service_id != service_id:
        return False
    if canonical_rule(waiver.rule) != canonical_rule(rule):
        return False
    if waiver.version_range is None:
        return True
    return version is not None and in_range(version, waiver.version_range)


def best_match(
    waivers: Iterable[Any], *, team_id: int, service_id: int, rule: str, version: str | None,
    at: datetime,
) -> Any | None:
    matches = [
        w for w in waivers
        if covers(w, team_id=team_id, service_id=service_id, rule=rule, version=version, at=at)
    ]
    if not matches:
        return None
    return min(matches, key=lambda w: (-w.expires_at.timestamp(), w.id))
