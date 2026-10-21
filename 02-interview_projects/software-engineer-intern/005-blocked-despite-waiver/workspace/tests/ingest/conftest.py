"""Sample payloads, and fakes (in ``sys.modules``) recording what ingest asks of
evaluation, audit and callbacks; those packages have their own tests."""

from __future__ import annotations

import copy
import sys
import types
from typing import Any

import pytest

from gatekeeper.core.contracts import Decision

FORGELINE_PAYLOAD: dict[str, Any] = {
    "schema": "forgeline/v2",
    "pipeline": {"id": "fl-88213", "url": "https://forgeline.mossbank.example.test/runs/88213"},
    "project": {"service": "payments-api"},
    "git": {"sha": "9f2c4e1d7a3b5c6d8e9f0a1b2c3d4e5f6a7b8c9d", "ref": "refs/heads/main"},
    "deploy": {"environment": "production", "version": "4.12.0"},
    "callback": {"url": "http://ci-mock:9100/callbacks/payments-api/payments-api"},
    "evidence": {
        "dependencies": [{"name": "ledgerkit", "version": "2.4.1", "ecosystem": "pypi",
                          "advisories": [{"id": "MBSA-2026-0141", "severity": "HIGH"}]}],
        "secrets_scan": {"findings": [{"detector": "generic-api-key", "file": "deploy/app.env",
                                       "line": 3}]},
        "sast": {"new_findings": {"critical": 0, "high": 1, "medium": 2, "low": 0},
                 "total_findings": {"critical": 0, "high": 4, "medium": 19, "low": 40}},
        "tests": {"passed": 412, "failed": 0, "skipped": 6},
        "signing": {"signed": True, "verified": True, "key_id": "mossbank-release-2026"},
    },
}

LEGACY_PAYLOAD: dict[str, Any] = {
    "runner": "legacy-runner/1.8", "service_name": "kyc-api", "build_id": "LR-20261202-0042",
    "git_commit": "4be1c0ffee4be1c0ffee4be1c0ffee4be1c0ffee", "git_branch": "main",
    "deploy_env": "prod", "app_version": "2.3.1",
    "callback": "http://ci-mock:9100/callbacks/kyc-platform/kyc-api",
    "vulns": [{"package": "pdfmint", "installed": "0.9.2", "id": "MBSA-2025-0310",
               "sev": "MODERATE"}],
    "secrets_found": 0, "sast_crit_new": 0, "sast_high_new": 1, "sast_medium_new": 3,
    "tests_total": 120, "tests_failed": 2, "tests_skipped": 0, "signed": "yes",
}


@pytest.fixture
def forgeline() -> dict[str, Any]:
    return copy.deepcopy(FORGELINE_PAYLOAD)


@pytest.fixture
def legacy() -> dict[str, Any]:
    return copy.deepcopy(LEGACY_PAYLOAD)


class Downstream:
    def __init__(self) -> None:
        self.decision = Decision("pass", [], policy_id=None, policy_version=None)
        self.evaluated: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.callbacks: list[dict[str, Any]] = []

    def evaluate(self, conn, **kwargs: Any) -> Decision:
        self.evaluated.append(kwargs)
        return self.decision

    def record(self, conn, **kwargs: Any) -> int:
        self.audit.append(kwargs)
        return len(self.audit)

    def enqueue(self, conn, **kwargs: Any) -> int:
        self.callbacks.append(kwargs)
        return len(self.callbacks)


@pytest.fixture
def downstream(monkeypatch) -> Downstream:
    fake = Downstream()
    for name, attr in [("gatekeeper.evaluation.service", "evaluate"),
                       ("gatekeeper.audit.service", "record"),
                       ("gatekeeper.callbacks.service", "enqueue")]:
        module = types.ModuleType(name)
        setattr(module, attr, getattr(fake, attr))
        monkeypatch.setitem(sys.modules, name, module)
    return fake
