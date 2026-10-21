"""Values passed between components (ingest -> evaluation -> waivers -> audit).

Shapes of the normalized evidence and the decision are documented in
docs/architecture.md, "Evidence" and "Decision model"; keep them in sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITIES = ("none", "low", "medium", "high", "critical")
EVIDENCE_KINDS = ("dependencies", "secrets", "sast", "tests", "signing")
SOURCES = ("forgeline_v2", "legacy")
OUTCOMES = ("pass", "warn", "block")


def severity_rank(severity: str) -> int:
    """0 for ``none`` .. 4 for ``critical``; raises ValueError on anything else."""
    return SEVERITIES.index(severity)


@dataclass(frozen=True)
class Submission:
    """One CI evaluation request after an ingest adapter normalized it."""

    source: str
    service: str  # service slug, unique within the team
    pipeline_id: str
    commit_sha: str
    branch: str
    environment: str
    version: str | None
    callback_url: str | None
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleResult:
    rule: str  # canonical rule id, e.g. "dependency.max_severity"
    outcome: str  # "pass" | "warn" | "block"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    waiver_id: int | None = None

    def as_reason(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "outcome": self.outcome,
            "message": self.message,
            "waiver_id": self.waiver_id,
            "details": self.details,
        }


@dataclass(frozen=True)
class Decision:
    decision: str  # "pass" | "warn" | "block"
    results: list[RuleResult]
    policy_id: int | None
    policy_version: int | None

    @property
    def reasons(self) -> list[dict[str, Any]]:
        """What ``evaluations.reasons`` stores: every result that is not a plain pass."""
        return [r.as_reason() for r in self.results if r.outcome != "pass"]
