from __future__ import annotations

import logging

import pytest

from gatekeeper.core.errors import ValidationFailed
from gatekeeper.ingest.adapters import legacy as legacy_adapter
from gatekeeper.ingest.adapters import to_submission
from gatekeeper.ingest.schemas import MAX_PACKAGES, MAX_STRING_LENGTH


def test_forgeline_v2_maps_to_normalized_evidence(forgeline):
    submission = to_submission(forgeline)

    assert (submission.source, submission.service, submission.pipeline_id) == (
        "forgeline_v2", "payments-api", "fl-88213")
    assert (submission.branch, submission.environment, submission.version) == (
        "main", "production", "4.12.0")
    assert submission.callback_url == "http://ci-mock:9100/callbacks/payments-api/payments-api"
    assert submission.evidence == {
        "dependencies": {"packages": [{"name": "ledgerkit", "version": "2.4.1", "ecosystem": "pypi",
                                       "vulnerabilities": [{"id": "MBSA-2026-0141",
                                                            "severity": "high"}]}]},
        "secrets": {"count": 1, "findings": [{"detector": "generic-api-key",
                                              "path": "deploy/app.env", "line": 3}]},
        "sast": {"new": {"critical": 0, "high": 1, "medium": 2, "low": 0},
                 "total": {"critical": 0, "high": 4, "medium": 19, "low": 40}},
        "tests": {"passed": 412, "failed": 0, "skipped": 6},
        "signing": {"signed": True, "verified": True, "key_id": "mossbank-release-2026"},
    }


@pytest.mark.parametrize(
    ("ref", "branch"),
    [("refs/heads/release/4.12", "release/4.12"), ("refs/tags/v4.12.0", "v4.12.0"),
     ("main", "main")],
)
def test_forgeline_ref_becomes_the_branch(forgeline, ref, branch):
    forgeline["git"]["ref"] = ref

    assert to_submission(forgeline).branch == branch


def test_forgeline_optional_parts_may_be_absent(forgeline):
    del forgeline["callback"], forgeline["deploy"]["version"]
    del forgeline["evidence"]["sast"], forgeline["evidence"]["signing"]
    forgeline["ci_extras"] = {"runner_pool": "eu-west"}

    submission = to_submission(forgeline)

    assert submission.callback_url is None and submission.version is None
    assert set(submission.evidence) == {"dependencies", "secrets", "tests"}


@pytest.mark.parametrize(
    ("path", "value", "field"),
    [(("git", "ref"), "refs/pull/12/merge", "git"),
     (("git", "sha"), "not-a-sha", "git"),
     (("deploy", "environment"), "prod", "deploy"),
     (("callback", "url"), "ftp://ci-mock/cb", "callback"),
     (("evidence", "dependencies", 0, "advisories", 0, "severity"), "SEVERE", "evidence")],
)
def test_forgeline_invalid_fields_are_422(forgeline, path, value, field):
    target = forgeline
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    with pytest.raises(ValidationFailed) as exc:
        to_submission(forgeline)

    assert exc.value.code == "validation_failed" and field in exc.value.details


def test_legacy_payload_maps_to_normalized_evidence(legacy):
    legacy["vulns"].append({"package": "pdfmint", "installed": "0.9.2", "id": "MBSA-2026-0002",
                            "sev": "CRITICAL"})
    submission = to_submission(legacy)

    assert (submission.source, submission.service, submission.pipeline_id) == (
        "legacy", "kyc-api", "LR-20261202-0042")
    assert (submission.environment, submission.version, submission.branch) == (
        "production", "2.3.1", "main")
    assert submission.evidence == {
        "dependencies": {"packages": [{"name": "pdfmint", "version": "0.9.2",
                                       "ecosystem": "unknown",
                                       "vulnerabilities": [
                                           {"id": "MBSA-2025-0310", "severity": "medium"},
                                           {"id": "MBSA-2026-0002", "severity": "critical"}]}]},
        "secrets": {"count": 0, "findings": []},
        "sast": {"new": {"critical": 0, "high": 1, "medium": 3, "low": 0}, "total": None},
        "tests": {"passed": 118, "failed": 2, "skipped": 0},
        "signing": {"signed": True, "verified": True, "key_id": None},
    }


@pytest.mark.parametrize(
    ("raw", "severity"),
    [("CRIT", "critical"), ("p1", "critical"), (" Sev2 ", "high"), ("IMPORTANT", "high"),
     ("moderate", "medium"), ("P3", "medium"), ("MINOR", "low"), ("SEV4", "low"),
     ("informational", "none"), ("", "none"), (None, "none")],
)
def test_legacy_severity_table(raw, severity):
    assert legacy_adapter.map_severity(raw) == severity


def test_legacy_unknown_severity_is_high_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="gatekeeper.ingest.adapters.legacy"):
        assert legacy_adapter.map_severity("URGENT", "MBSA-2026-0007") == "high"

    assert [r.getMessage() for r in caplog.records] == ["ingest.legacy_unknown_severity"]


def test_legacy_collects_every_error(legacy):
    del legacy["build_id"]
    assert to_submission({**legacy, "build_id": "b1", "deploy_env": "stg"}).environment == "staging"
    legacy.update(deploy_env="qa", tests_failed=150, signed="maybe", sast_high_new=-1)

    with pytest.raises(ValidationFailed) as exc:
        to_submission(legacy)

    assert set(exc.value.details) == {"build_id", "deploy_env", "tests_total", "signed",
                                      "sast_high_new"}


def test_too_many_packages_is_evidence_too_large(forgeline):
    package = {"name": "pkg", "version": "1.0.0", "ecosystem": "npm"}
    forgeline["evidence"]["dependencies"] = [package] * (MAX_PACKAGES + 1)

    with pytest.raises(ValidationFailed) as exc:
        to_submission(forgeline)

    assert exc.value.code == "evidence_too_large"
    assert exc.value.details == {"limit": MAX_PACKAGES, "count": MAX_PACKAGES + 1}


def test_long_strings_are_evidence_too_large(legacy):
    legacy["vulns"][0]["id"] = "X" * (MAX_STRING_LENGTH + 1)

    with pytest.raises(ValidationFailed) as exc:
        to_submission(legacy)

    assert exc.value.code == "evidence_too_large"
    assert exc.value.details["path"] == "$.vulns[0].id"

