"""Compiled rules -> results -> one decision (docs/architecture.md, "Decision model").

* A rule whose ``when`` does not match the submission is skipped: no result.
* A rule whose evidence kind is absent yields its ``action`` with
  ``details.missing = true``.
* Otherwise the rule passes, or yields its ``action`` when violated.
* Aggregation: ``block`` beats ``warn`` beats ``pass``; no result at all is
  ``pass``. Waivers are applied by the service before aggregating.
"""

from __future__ import annotations

from gatekeeper.core.contracts import RuleResult, Submission
from gatekeeper.evaluation.compiler import CompiledPolicy

_RANK = {"pass": 0, "warn": 1, "block": 2}

MISSING_POLICY = RuleResult(
    "policy.missing", "warn", "team has no policy; publish one with POST /v1/policies"
)


def run_rules(policy: CompiledPolicy, submission: Submission) -> list[RuleResult]:
    results: list[RuleResult] = []
    for rule in policy.rules:
        if not rule.applies_to(submission):
            continue
        data = submission.evidence.get(rule.evidence)
        if data is None:
            results.append(RuleResult(
                rule.id, rule.action, f"no {rule.evidence} evidence in the submission",
                {"missing": True},
            ))
            continue
        verdict = rule.check(rule.params, data)
        outcome = "pass" if verdict.ok else rule.action
        results.append(RuleResult(rule.id, outcome, verdict.message, verdict.details))
    return results


def aggregate(results: list[RuleResult]) -> str:
    return max((r.outcome for r in results), key=_RANK.__getitem__, default="pass")
