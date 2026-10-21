"""Evaluation test helpers.

The waiver and audit services are replaced by recording fakes so these tests
pin down what evaluation itself does; their own packages test the real ones.
"""

from __future__ import annotations

import copy
import sys
import types
from dataclasses import replace
from typing import Any

import pytest

from gatekeeper.core.contracts import RuleResult, Submission
from gatekeeper.evaluation import compiler
from tests.factories import PASSING_EVIDENCE


def make_submission(evidence: dict[str, Any] | None = None, **overrides: Any) -> Submission:
    values: dict[str, Any] = {
        "source": "forgeline_v2", "service": "payments-api", "pipeline_id": "fl-88213",
        "commit_sha": "9f2c4e1d" * 5, "branch": "main", "environment": "production",
        "version": "4.12.0", "callback_url": None,
        "evidence": copy.deepcopy(PASSING_EVIDENCE if evidence is None else evidence),
    }
    values.update(overrides)
    return Submission(**values)


class FakeWaivers:
    """Covers the violated results whose rule is in ``covered`` (rule -> waiver id)."""

    def __init__(self) -> None:
        self.covered: dict[str, int] = {}
        self.calls: list[dict[str, Any]] = []

    def apply_waivers(self, conn, *, team_id, service_id, version, results) -> list[RuleResult]:
        self.calls.append({"team_id": team_id, "service_id": service_id, "version": version,
                           "rules": [r.rule for r in results]})
        return [
            replace(r, outcome="warn", waiver_id=self.covered[r.rule],
                    message=f"waived: {r.message}")
            if r.outcome != "pass" and r.rule in self.covered else r
            for r in results
        ]


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(self, conn, **event: Any) -> int:
        self.events.append(event)
        return len(self.events)


def _install(monkeypatch, name: str, **functions: Any) -> None:
    module = types.ModuleType(name)
    module.__dict__.update(functions)
    monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture(autouse=True)
def waivers(monkeypatch) -> FakeWaivers:
    fake = FakeWaivers()
    _install(monkeypatch, "gatekeeper.waivers.service", apply_waivers=fake.apply_waivers)
    return fake


@pytest.fixture(autouse=True)
def audit(monkeypatch) -> FakeAudit:
    fake = FakeAudit()
    _install(monkeypatch, "gatekeeper.audit.service", record=fake.record)
    return fake


@pytest.fixture(autouse=True)
def policy_cache():
    compiler.cache().clear()
    yield compiler.cache()
    compiler.cache().clear()
