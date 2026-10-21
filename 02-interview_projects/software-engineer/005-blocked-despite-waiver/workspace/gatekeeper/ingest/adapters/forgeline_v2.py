"""Forgeline CI payload v2 (``schema: forgeline/v2``) -> ``Submission``."""

from __future__ import annotations

from typing import Any

from marshmallow import ValidationError

from gatekeeper.core.contracts import Submission
from gatekeeper.core.errors import ValidationFailed
from gatekeeper.ingest.schemas import ForgelinePayloadSchema

SOURCE = "forgeline_v2"
_REF_PREFIXES = ("refs/heads/", "refs/tags/")
_schema = ForgelinePayloadSchema()


def branch_from_ref(ref: str) -> str:
    """``refs/heads/main`` -> ``main``, ``refs/tags/v4.12.0`` -> ``v4.12.0``."""
    for prefix in _REF_PREFIXES:
        if ref.startswith(prefix) and len(ref) > len(prefix):
            return ref[len(prefix) :]
    if ref.startswith("refs/"):
        raise ValidationFailed(
            "git.ref must be a branch or a tag",
            details={"git": {"ref": [f"unsupported ref {ref!r}"]}},
        )
    return ref


def _dependencies(items: list[dict[str, Any]]) -> dict[str, Any]:
    # advisories are already {"id", "severity"} with the severity lower-cased by the schema
    packages = [{"name": item["name"], "version": item["version"], "ecosystem": item["ecosystem"],
                 "vulnerabilities": item["advisories"]} for item in items]
    return {"packages": packages}


def _secrets(scan: dict[str, Any]) -> dict[str, Any]:
    findings = [{"detector": f["detector"], "path": f["file"], "line": f.get("line")}
                for f in scan["findings"]]
    return {"count": len(findings), "findings": findings}


def _evidence(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    if "dependencies" in raw:
        evidence["dependencies"] = _dependencies(raw["dependencies"])
    if "secrets_scan" in raw:
        evidence["secrets"] = _secrets(raw["secrets_scan"])
    if "sast" in raw:
        evidence["sast"] = {"new": raw["sast"]["new_findings"],
                            "total": raw["sast"]["total_findings"]}
    if "tests" in raw:
        evidence["tests"] = dict(raw["tests"])
    if "signing" in raw:
        evidence["signing"] = dict(raw["signing"])
    return evidence


def to_submission(payload: dict[str, Any]) -> Submission:
    try:
        data = _schema.load(payload)
    except ValidationError as exc:
        raise ValidationFailed("forgeline/v2 payload is invalid", details=exc.messages) from exc
    callback = data["callback"]
    return Submission(
        source=SOURCE,
        service=data["project"]["service"],
        pipeline_id=data["pipeline"]["id"],
        commit_sha=data["git"]["sha"],
        branch=branch_from_ref(data["git"]["ref"]),
        environment=data["deploy"]["environment"],
        version=data["deploy"]["version"],
        callback_url=callback["url"] if callback else None,
        evidence=_evidence(data["evidence"]),
    )
