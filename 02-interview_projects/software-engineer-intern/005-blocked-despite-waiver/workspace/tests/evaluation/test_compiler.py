from __future__ import annotations

from types import SimpleNamespace

from gatekeeper.evaluation import compiler
from gatekeeper.evaluation.compiler import PolicyCache
from tests.factories import DEFAULT_POLICY

WARN_ONLY = "policy: 1\nrules:\n  - {id: secrets.allowed, action: warn}\n"


def _row(policy_id: int, team_id: int, version: int, source: str = DEFAULT_POLICY):
    return SimpleNamespace(id=policy_id, team_id=team_id, version=version, source=source)


def test_compiled_policy_carries_its_row_identity():
    compiled = compiler.compiled_for(_row(41, 3, 7))

    assert (compiled.policy_id, compiled.team_id, compiled.version) == (41, 3, 7)
    assert [r.evidence for r in compiled.rules] == [
        "dependencies", "secrets", "sast", "tests", "signing",
    ]


def test_same_version_is_compiled_once(policy_cache):
    first = compiler.compiled_for(_row(1, 1, 1))
    second = compiler.compiled_for(_row(1, 1, 1))

    assert second is first
    assert (policy_cache.misses, policy_cache.hits) == (1, 1)


def test_new_version_is_a_new_entry_and_versions_do_not_mix(policy_cache):
    v1 = compiler.compiled_for(_row(1, 1, 1))
    v2 = compiler.compiled_for(_row(2, 1, 2, WARN_ONLY))

    assert v2 is not v1
    assert [r.id for r in v2.rules] == ["secrets.allowed"]
    assert compiler.compiled_for(_row(1, 1, 1)) is v1
    assert len(policy_cache) == 2


def test_same_version_number_of_another_team_is_separate():
    mine = compiler.compiled_for(_row(1, 1, 1))
    theirs = compiler.compiled_for(_row(2, 2, 1, WARN_ONLY))

    assert theirs is not mine and theirs.team_id == 2


def test_reused_key_with_a_different_row_is_recompiled(policy_cache):
    compiler.compiled_for(_row(1, 1, 1))

    recompiled = compiler.compiled_for(_row(9, 1, 1, WARN_ONLY))  # e.g. after a restore

    assert recompiled.policy_id == 9 and len(recompiled.rules) == 1
    assert policy_cache.misses == 2


def test_invalidate_team_drops_only_that_team(policy_cache):
    compiler.compiled_for(_row(1, 1, 1))
    compiler.compiled_for(_row(2, 1, 2))
    compiler.compiled_for(_row(3, 2, 1))

    assert compiler.invalidate_team(1) == 2
    assert (1, 1) not in policy_cache and (2, 1) in policy_cache


def test_least_recently_used_entry_is_evicted_at_capacity():
    cache = PolicyCache(maxsize=2)
    cache.get(_row(1, 1, 1))
    cache.get(_row(2, 2, 1))
    cache.get(_row(1, 1, 1))  # team 1 is now the most recent

    cache.get(_row(3, 3, 1))

    assert (1, 1) in cache and (3, 1) in cache and (2, 1) not in cache
