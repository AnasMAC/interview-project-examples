"""Schemas of the evidence API and the evidence limits (docs/architecture.md,
"Evidence"): the API enforces the body size (413), the rest is 422 ``evidence_too_large``."""

from __future__ import annotations

import re
from typing import Any

from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate

from gatekeeper.core.contracts import SEVERITIES
from gatekeeper.core.errors import ValidationFailed

MAX_PACKAGES = 5_000
MAX_VULNERABILITIES_PER_PACKAGE = 200
MAX_SECRET_FINDINGS = 1_000
MAX_STRING_LENGTH = 512
MAX_VERSION_LENGTH = 64  # evaluations.version
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")
ENVIRONMENTS = ("production", "staging", "development")


def too_large(what: str, limit: int, **details: Any) -> ValidationFailed:
    return ValidationFailed(
        f"{what} exceeds the limit of {limit}",
        code="evidence_too_large",
        details={"limit": limit, **details},
    )


def enforce_string_lengths(payload: Any) -> None:
    """Reject any string value longer than ``MAX_STRING_LENGTH`` (iterative walk)."""
    stack: list[tuple[str, Any]] = [("$", payload)]
    while stack:
        path, value = stack.pop()
        if isinstance(value, str):
            if len(value) > MAX_STRING_LENGTH:
                raise too_large(f"string at {path}", MAX_STRING_LENGTH, path=path)
        elif isinstance(value, dict):
            stack.extend((f"{path}.{key}", item) for key, item in value.items())
        elif isinstance(value, list):
            stack.extend((f"{path}[{i}]", item) for i, item in enumerate(value))


def enforce_limits(evidence: dict[str, dict[str, Any]]) -> None:
    """Count limits on normalized evidence, whichever adapter produced it."""
    packages = evidence.get("dependencies", {}).get("packages", [])
    if len(packages) > MAX_PACKAGES:
        raise too_large("dependencies", MAX_PACKAGES, count=len(packages))
    for package in packages:
        count = len(package["vulnerabilities"])
        if count > MAX_VULNERABILITIES_PER_PACKAGE:
            raise too_large(
                f"vulnerabilities of {package['name']}",
                MAX_VULNERABILITIES_PER_PACKAGE,
                count=count,
            )
    findings = evidence.get("secrets", {}).get("findings", [])
    if len(findings) > MAX_SECRET_FINDINGS:
        raise too_large("secret findings", MAX_SECRET_FINDINGS, count=len(findings))


class Severity(fields.String):
    """Severity in any letter case on the wire, lower case once loaded."""

    def _deserialize(self, value: Any, attr: str | None, data: Any, **kwargs: Any) -> str:
        severity = super()._deserialize(value, attr, data, **kwargs).strip().lower()
        if severity not in SEVERITIES:
            raise ValidationError(f"must be one of: {', '.join(s.upper() for s in SEVERITIES)}")
        return severity


def _text(**kwargs: Any) -> fields.String:
    return fields.String(validate=validate.Length(min=1), **kwargs)


def _count(**kwargs: Any) -> fields.Integer:
    return fields.Integer(strict=True, validate=validate.Range(min=0), **kwargs)


class _Lenient(Schema):
    """Forgeline adds fields between minor releases; ignore what we do not use."""

    class Meta:
        unknown = EXCLUDE


class _Advisory(_Lenient):
    id = _text(required=True)
    severity = Severity(required=True)


class _Dependency(_Lenient):
    name = _text(required=True)
    version = _text(required=True)
    ecosystem = _text(required=True)
    advisories = fields.List(fields.Nested(_Advisory), load_default=list)


class _SecretFinding(_Lenient):
    detector = _text(required=True)
    file = _text(required=True)
    line = fields.Integer(strict=True, validate=validate.Range(min=1), allow_none=True)


class _SecretsScan(_Lenient):
    findings = fields.List(fields.Nested(_SecretFinding), required=True)


class _SastCounts(_Lenient):
    critical = _count(load_default=0)
    high = _count(load_default=0)
    medium = _count(load_default=0)
    low = _count(load_default=0)


class _Sast(_Lenient):
    new_findings = fields.Nested(_SastCounts, required=True)
    total_findings = fields.Nested(_SastCounts, allow_none=True, load_default=None)


class _Tests(_Lenient):
    passed = _count(required=True)
    failed = _count(required=True)
    skipped = _count(load_default=0)


class _Signing(_Lenient):
    signed = fields.Boolean(required=True)
    verified = fields.Boolean(required=True)
    key_id = _text(allow_none=True, load_default=None)


class _Evidence(_Lenient):
    dependencies = fields.List(fields.Nested(_Dependency))
    secrets_scan = fields.Nested(_SecretsScan)
    sast = fields.Nested(_Sast)
    tests = fields.Nested(_Tests)
    signing = fields.Nested(_Signing)


class _Pipeline(_Lenient):
    id = _text(required=True)


class _Project(_Lenient):
    service = _text(required=True)


class _Git(_Lenient):
    sha = fields.String(required=True, validate=validate.Regexp(COMMIT_SHA))
    ref = _text(required=True)


class _Deploy(_Lenient):
    environment = fields.String(required=True, validate=validate.OneOf(ENVIRONMENTS))
    version = fields.String(
        allow_none=True, load_default=None, validate=validate.Length(1, MAX_VERSION_LENGTH)
    )


class _Callback(_Lenient):
    url = fields.Url(required=True, require_tld=False, schemes={"http", "https"})


class ForgelinePayloadSchema(_Lenient):
    schema = fields.String(required=True, validate=validate.Equal("forgeline/v2"))
    pipeline = fields.Nested(_Pipeline, required=True)
    project = fields.Nested(_Project, required=True)
    git = fields.Nested(_Git, required=True)
    deploy = fields.Nested(_Deploy, required=True)
    callback = fields.Nested(_Callback, allow_none=True, load_default=None)
    evidence = fields.Nested(_Evidence, load_default=dict)


class EvaluationViewSchema(Schema):
    """The evaluation view: POST/GET responses and the callback payload."""

    id = fields.Integer()
    team = fields.String()
    service = fields.String()
    source = fields.String()
    pipeline_id = fields.String()
    commit_sha = fields.String()
    branch = fields.String()
    environment = fields.String()
    version = fields.String(allow_none=True)
    decision = fields.String()
    reasons = fields.List(fields.Dict())
    policy_version = fields.Integer(allow_none=True)
    created_at = fields.String()  # ISO 8601, UTC, seconds
