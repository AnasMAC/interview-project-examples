"""Payload adapters: each CI system's JSON -> the normalized ``Submission``."""

from __future__ import annotations

from typing import Any

from gatekeeper.core.contracts import Submission
from gatekeeper.core.errors import ValidationFailed
from gatekeeper.ingest.adapters import forgeline_v2, legacy
from gatekeeper.ingest.schemas import enforce_limits, enforce_string_lengths

FORGELINE_SCHEMA = "forgeline/v2"
LEGACY_RUNNER_PREFIX = "legacy-runner/"


def to_submission(payload: dict[str, Any]) -> Submission:
    """Pick the adapter from the payload's own marker and apply the evidence limits."""
    runner = payload.get("runner")
    if payload.get("schema") == FORGELINE_SCHEMA:
        adapter = forgeline_v2.to_submission
    elif isinstance(runner, str) and runner.startswith(LEGACY_RUNNER_PREFIX):
        adapter = legacy.to_submission
    else:
        raise ValidationFailed(
            "payload is neither forgeline/v2 nor legacy-runner",
            code="unknown_payload_format",
            details={"expected": ["schema: forgeline/v2", "runner: legacy-runner/*"]},
        )
    enforce_string_lengths(payload)
    submission = adapter(payload)
    enforce_limits(submission.evidence)
    return submission
