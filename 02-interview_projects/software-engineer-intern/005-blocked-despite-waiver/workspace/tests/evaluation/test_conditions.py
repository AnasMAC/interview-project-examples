from __future__ import annotations

import pytest

from gatekeeper.evaluation.conditions import Condition, branch_matches, normalize_environment


@pytest.mark.parametrize(
    ("patterns", "branch", "matches"),
    [
        (("main",), "main", True),
        (("main",), "main2", False),
        (("main",), "Main", False),  # case-sensitive
        (("release/*",), "release/4.12", True),
        (("release/*",), "release/4.12/hotfix-1", True),  # fnmatch: * crosses /
        (("release/*",), "release", False),
        (("release/*",), "releases/4.12", False),
        (("release/4.1?",), "release/4.12", True),
        (("release/[0-9]*",), "release/next", False),
        (("feature/*", "main"), "main", True),
        (("*",), "anything/at/all", True),
    ],
)
def test_branch_globs(patterns, branch, matches):
    assert branch_matches(patterns, branch) is matches


@pytest.mark.parametrize(
    ("condition", "branch", "environment", "matches"),
    [
        (Condition(), "feature/x", "development", True),
        (Condition(branches=("main",)), "main", "staging", True),
        (Condition(branches=("main",)), "feature/x", "production", False),
        (Condition(environments=("production",)), "feature/x", "production", True),
        (Condition(environments=("production",)), "main", "staging", False),
        (Condition(environments=("staging", "production")), "main", "staging", True),
        (Condition(("main", "release/*"), ("production",)), "release/4.12", "production", True),
        (Condition(("main", "release/*"), ("production",)), "release/4.12", "staging", False),
        (Condition(("main", "release/*"), ("production",)), "feature/x", "production", False),
    ],
)
def test_both_dimensions_must_match(condition, branch, environment, matches):
    assert condition.matches(branch=branch, environment=environment) is matches


@pytest.mark.parametrize(
    ("name", "canonical"),
    [("production", "production"), ("prod", "production"), (" PROD ", "production"),
     ("stg", "staging"), ("dev", "development"), ("qa", None), ("", None)],
)
def test_environment_names_and_legacy_aliases(name, canonical):
    assert normalize_environment(name) == canonical
