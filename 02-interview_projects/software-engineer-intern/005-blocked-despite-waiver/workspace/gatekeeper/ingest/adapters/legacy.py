"""Legacy runner payload (``runner: legacy-runner/1.x``) -> Submission.

The legacy runner sends one flat JSON object. Still used by kyc-platform,
treasury-tools and data-pipelines until they move to Forgeline.

Author: Ana Petrović
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from gatekeeper.core.contracts import Submission
from gatekeeper.core.errors import ValidationFailed
from gatekeeper.core.logging import get_logger
from gatekeeper.ingest.schemas import COMMIT_SHA, MAX_VERSION_LENGTH

log = get_logger(__name__)

SOURCE = "legacy"

# severity strings seen from the legacy scanners (upper-cased + trimmed before lookup)
SEVERITY_MAP = {
    **dict.fromkeys(["CRITICAL", "CRIT", "SEV1", "P1"], "critical"),
    **dict.fromkeys(["HIGH", "IMPORTANT", "SEV2", "P2"], "high"),
    **dict.fromkeys(["MEDIUM", "MODERATE", "MED", "SEV3", "P3"], "medium"),
    **dict.fromkeys(["LOW", "MINOR", "SEV4", "P4"], "low"),
    **dict.fromkeys(["NONE", "INFO", "INFORMATIONAL", "NEGLIGIBLE", ""], "none"),
}

ENV_MAP = {"prod": "production", "stg": "staging", "dev": "development"}


def map_severity(raw: Any, vuln_id: str = "") -> str:
    if raw is None:
        raw = ""
    key = str(raw).strip().upper()
    if key in SEVERITY_MAP:
        return SEVERITY_MAP[key]
    # unknown severity: be safe and treat it as high
    log.warning(
        "ingest.legacy_unknown_severity", extra={"severity": str(raw)[:32], "vuln_id": vuln_id}
    )
    return "high"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def to_submission(payload: dict[str, Any]) -> Submission:
    errors: dict[str, list[str]] = {}
    fields: dict[str, Any] = {}
    vulns: list[dict[str, Any]] | None = None
    sast: dict[str, int] = {}
    tests: dict[str, int] = {}

    for key, value in payload.items():
        if key == "service_name":
            if isinstance(value, str) and value.strip():
                fields["service"] = value.strip()
            else:
                errors[key] = ["must be a non-empty string"]
        elif key == "build_id":
            if isinstance(value, str) and value.strip():
                fields["pipeline_id"] = value.strip()
            else:
                errors[key] = ["must be a non-empty string"]
        elif key == "git_commit":
            if isinstance(value, str) and COMMIT_SHA.match(value):
                fields["commit_sha"] = value
            else:
                errors[key] = ["must be a hex commit sha"]
        elif key == "git_branch":
            if isinstance(value, str) and value.strip():
                fields["branch"] = value.strip()
            else:
                errors[key] = ["must be a non-empty string"]
        elif key == "deploy_env":
            if isinstance(value, str) and value.strip().lower() in ENV_MAP:
                fields["environment"] = ENV_MAP[value.strip().lower()]
            else:
                errors[key] = ["must be one of: prod, stg, dev"]
        elif key == "app_version":
            if value is None or value == "":
                fields["version"] = None
            elif isinstance(value, str) and len(value) <= MAX_VERSION_LENGTH:
                fields["version"] = value.strip()
            else:
                errors[key] = [f"must be a string of at most {MAX_VERSION_LENGTH} characters"]
        elif key == "callback":
            if value is None or value == "":
                fields["callback_url"] = None
            elif isinstance(value, str) and urlparse(value).scheme in ("http", "https") \
                    and urlparse(value).netloc:
                fields["callback_url"] = value
            else:
                errors[key] = ["must be an http(s) URL"]
        elif key == "vulns":
            if isinstance(value, list) and all(isinstance(v, dict) for v in value):
                vulns = value
            else:
                errors[key] = ["must be a list of objects"]
        elif key == "secrets_found":
            if _is_int(value):
                fields["secrets_found"] = value
            else:
                errors[key] = ["must be a non-negative integer"]
        elif key in ("sast_crit_new", "sast_high_new", "sast_medium_new", "sast_low_new"):
            if _is_int(value):
                sast[key] = value
            else:
                errors[key] = ["must be a non-negative integer"]
        elif key in ("tests_total", "tests_failed", "tests_skipped"):
            if _is_int(value):
                tests[key] = value
            else:
                errors[key] = ["must be a non-negative integer"]
        elif key == "signed":
            if value is True or (isinstance(value, str) and value.strip().lower() == "yes"):
                fields["signed"] = True
            elif value is False or (isinstance(value, str) and value.strip().lower() == "no"):
                fields["signed"] = False
            else:
                errors[key] = ["must be yes or no"]
        else:
            # old runner versions send extra stuff (agent_host, duration_s...), ignore it
            continue

    for required in ("service_name", "build_id", "git_commit", "git_branch", "deploy_env"):
        if required not in payload:
            errors[required] = ["missing required field"]

    evidence: dict[str, dict[str, Any]] = {}

    if vulns is not None:
        packages: dict[tuple[str, str], dict[str, Any]] = {}
        for i, v in enumerate(vulns):
            name, installed, vuln_id = v.get("package"), v.get("installed"), v.get("id")
            if not all(isinstance(x, str) and x for x in (name, installed, vuln_id)):
                errors[f"vulns[{i}]"] = ["package, installed and id must be non-empty strings"]
                continue
            if (name, installed) not in packages:
                packages[(name, installed)] = {
                    "name": name,
                    "version": installed,
                    "ecosystem": v.get("ecosystem") or "unknown",
                    "vulnerabilities": [],
                }
            packages[(name, installed)]["vulnerabilities"].append(
                {"id": vuln_id, "severity": map_severity(v.get("sev"), vuln_id)}
            )
        evidence["dependencies"] = {"packages": list(packages.values())}

    if "secrets_found" in fields:
        # legacy runner only reports a count, no details
        evidence["secrets"] = {"count": fields.pop("secrets_found"), "findings": []}

    if sast:
        evidence["sast"] = {
            "new": {
                "critical": sast.get("sast_crit_new", 0),
                "high": sast.get("sast_high_new", 0),
                "medium": sast.get("sast_medium_new", 0),
                "low": sast.get("sast_low_new", 0),
            },
            "total": None,
        }

    if tests:
        failed = tests.get("tests_failed", 0)
        skipped = tests.get("tests_skipped", 0)
        passed = tests.get("tests_total", 0) - failed - skipped
        if passed < 0:
            errors["tests_total"] = ["must be >= tests_failed + tests_skipped"]
        else:
            evidence["tests"] = {"passed": passed, "failed": failed, "skipped": skipped}

    if "signed" in fields:
        signed = fields.pop("signed")
        # the runner verifies the signature itself before sending "yes"
        evidence["signing"] = {"signed": signed, "verified": signed, "key_id": None}

    if errors:
        raise ValidationFailed("legacy runner payload is invalid", details=errors)

    return Submission(
        source=SOURCE,
        service=fields["service"],
        pipeline_id=fields["pipeline_id"],
        commit_sha=fields["commit_sha"],
        branch=fields["branch"],
        environment=fields["environment"],
        version=fields.get("version"),
        callback_url=fields.get("callback_url"),
        evidence=evidence,
    )
