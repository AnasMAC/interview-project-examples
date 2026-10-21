from __future__ import annotations

import pytest

from gatekeeper.core.contracts import RuleResult
from gatekeeper.evaluation import evaluator
from gatekeeper.evaluation.compiler import compile_source
from tests.evaluation.conftest import make_submission
from tests.factories import DEFAULT_POLICY, PASSING_EVIDENCE

BRANCH_POLICY = """\
policy: 1
rules:
  - {id: secrets.allowed, max: 0, action: warn}
  - {id: signing.required, when: {branches: [main, 'release/*'], environments: [production]}}
  - {id: tests.min_pass_rate, min: 0.9, action: warn, when: {environments: [staging]}}
"""


def _outcomes(results: list[RuleResult]) -> list[tuple[str, str]]:
    return [(r.rule, r.outcome) for r in results]


def test_passing_evidence_passes_every_default_rule_in_policy_order():
    results = evaluator.run_rules(compile_source(DEFAULT_POLICY), make_submission())

    assert _outcomes(results) == [
        ("dependency.max_severity", "pass"), ("secrets.allowed", "pass"),
        ("sast.new_high_max", "pass"), ("tests.min_pass_rate", "pass"),
        ("signing.required", "pass"),
    ]
    assert evaluator.aggregate(results) == "pass"


def test_violations_take_the_rule_action():
    evidence = {**PASSING_EVIDENCE,
                "sast": {"new": {"critical": 0, "high": 2, "medium": 0, "low": 0}, "total": None},
                "secrets": {"count": 1, "findings": []}}

    results = evaluator.run_rules(compile_source(DEFAULT_POLICY), make_submission(evidence))

    assert [(r.rule, r.outcome) for r in results if r.outcome != "pass"] == [
        ("secrets.allowed", "block"), ("sast.new_high_max", "warn"),
    ]
    assert evaluator.aggregate(results) == "block"


@pytest.mark.parametrize("kind", list(PASSING_EVIDENCE))
def test_missing_evidence_yields_the_action_with_missing_flag(kind):
    evidence = {k: v for k, v in PASSING_EVIDENCE.items() if k != kind}

    results = evaluator.run_rules(compile_source(DEFAULT_POLICY), make_submission(evidence))

    [missing] = [r for r in results if r.details.get("missing")]
    expected_action = "warn" if kind == "sast" else "block"
    assert missing.outcome == expected_action
    assert missing.details == {"missing": True}
    assert missing.message == f"no {kind} evidence in the submission"


@pytest.mark.parametrize(
    ("branch", "environment", "expected"),
    [
        ("main", "production", ["secrets.allowed", "signing.required"]),
        ("release/4.12", "production", ["secrets.allowed", "signing.required"]),
        ("feature/x", "production", ["secrets.allowed"]),
        ("main", "staging", ["secrets.allowed", "tests.min_pass_rate"]),
        ("main", "development", ["secrets.allowed"]),
    ],
)
def test_rules_whose_condition_does_not_match_produce_no_result(branch, environment, expected):
    submission = make_submission({}, branch=branch, environment=environment)

    results = evaluator.run_rules(compile_source(BRANCH_POLICY), submission)

    assert [r.rule for r in results] == expected


def test_skipped_rule_does_not_need_its_evidence():
    submission = make_submission({"secrets": {"count": 0, "findings": []}}, branch="feature/x")

    results = evaluator.run_rules(compile_source(BRANCH_POLICY), submission)

    assert _outcomes(results) == [("secrets.allowed", "pass")]


def _result(outcome: str) -> RuleResult:
    return RuleResult("secrets.allowed", outcome, "m")


@pytest.mark.parametrize(
    ("outcomes", "decision"),
    [
        ([], "pass"),
        (["pass"], "pass"),
        (["pass", "pass"], "pass"),
        (["pass", "warn"], "warn"),
        (["warn", "pass", "warn"], "warn"),
        (["block", "pass"], "block"),
        (["warn", "block"], "block"),
        (["block", "warn", "pass"], "block"),
    ],
)
def test_block_beats_warn_beats_pass(outcomes, decision):
    assert evaluator.aggregate([_result(o) for o in outcomes]) == decision
