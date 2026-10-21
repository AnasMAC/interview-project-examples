"""``Policy`` -> ``CompiledPolicy`` and the per-version compile cache.

Policy rows are never updated (ADR 0002), so a compiled policy is cached under
``(team_id, version)``. ``evaluate`` always reads the team's active version
from the database first and then asks the cache, so publishing a new version
is picked up by every gunicorn worker on its next evaluation, even though
each worker has its own cache. ``invalidate_team`` (called on publish) only
frees the superseded versions in the publishing worker.

An entry is reused only if the row's id and source are those it was compiled
from: a database restored or truncated with ``RESTART IDENTITY`` can reuse a
``(team_id, version)`` pair for a different policy.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row

from gatekeeper.core.contracts import Submission
from gatekeeper.evaluation.conditions import Condition
from gatekeeper.evaluation.dsl import Policy, parse_policy
from gatekeeper.evaluation.rules import RULES, Verdict

DEFAULT_CACHE_SIZE = 256


@dataclass(frozen=True)
class CompiledRule:
    id: str
    action: str
    evidence: str
    params: dict[str, Any]
    when: Condition | None
    check: Callable[[dict[str, Any], dict[str, Any]], Verdict]

    def applies_to(self, submission: Submission) -> bool:
        if self.when is None:
            return True
        return self.when.matches(branch=submission.branch, environment=submission.environment)


@dataclass(frozen=True)
class CompiledPolicy:
    policy_id: int | None  # None for a draft (dry run with a source)
    team_id: int | None
    version: int | None
    rules: tuple[CompiledRule, ...]
    warnings: tuple[str, ...] = ()


def compile_policy(
    policy: Policy, *, policy_id: int | None = None, team_id: int | None = None,
    version: int | None = None,
) -> CompiledPolicy:
    rules = tuple(
        CompiledRule(spec.id, spec.action, RULES[spec.id].evidence, spec.params, spec.when,
                     RULES[spec.id].check)
        for spec in policy.rules
    )
    return CompiledPolicy(policy_id, team_id, version, rules, policy.warnings)


def compile_source(source: str, **ids: Any) -> CompiledPolicy:
    """Parse and compile; raises ``ValidationFailed(code="invalid_policy")``."""
    return compile_policy(parse_policy(source), **ids)


class PolicyCache:
    def __init__(self, maxsize: int = DEFAULT_CACHE_SIZE) -> None:
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0
        self._entries: OrderedDict[tuple[int, int], tuple[str, CompiledPolicy]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, row: Row) -> CompiledPolicy:
        """Compiled policy for a ``policies`` row."""
        key = (row.team_id, row.version)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[1].policy_id == row.id and entry[0] == row.source:
                self._entries.move_to_end(key)
                self.hits += 1
                return entry[1]
            self.misses += 1
        compiled = compile_source(row.source, policy_id=row.id, team_id=row.team_id,
                                  version=row.version)
        with self._lock:
            self._entries[key] = (row.source, compiled)
            self._entries.move_to_end(key)
            while len(self._entries) > self.maxsize:
                self._entries.popitem(last=False)
        return compiled

    def invalidate_team(self, team_id: int) -> int:
        with self._lock:
            stale = [key for key in self._entries if key[0] == team_id]
            for key in stale:
                del self._entries[key]
        return len(stale)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self.hits = self.misses = 0

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: tuple[int, int]) -> bool:
        return key in self._entries


_cache = PolicyCache()


def cache() -> PolicyCache:
    return _cache


def compiled_for(row: Row) -> CompiledPolicy:
    return _cache.get(row)


def invalidate_team(team_id: int) -> int:
    return _cache.invalidate_team(team_id)
