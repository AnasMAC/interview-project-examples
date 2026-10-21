"""Request and response schemas of ``/v1/policies``.

The dry-run body carries evidence in the *normalized* shape of
docs/architecture.md ("Evidence"), not a CI payload, so the developer portal
can ask "what if" without speaking Forgeline. Limits mirror ingest's.
"""

from __future__ import annotations

from marshmallow import Schema, ValidationError, fields, validate, validates_schema

from gatekeeper.core.contracts import SEVERITIES
from gatekeeper.evaluation.conditions import ENVIRONMENTS
from gatekeeper.evaluation.dsl import MAX_SOURCE_BYTES

_text = validate.Length(min=1, max=512)
_count = validate.Range(min=0)


def _counter(**kw: object) -> fields.Integer:
    return fields.Integer(strict=True, validate=_count, **kw)


class PublishPolicySchema(Schema):
    source = fields.String(required=True, validate=validate.Length(min=1, max=MAX_SOURCE_BYTES))
    comment = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=500))


class _Vulnerability(Schema):
    id = fields.String(required=True, validate=_text)
    severity = fields.String(required=True, validate=validate.OneOf(SEVERITIES))


class _Package(Schema):
    name = fields.String(required=True, validate=_text)
    version = fields.String(required=True, validate=_text)
    ecosystem = fields.String(load_default="unknown", validate=_text)
    vulnerabilities = fields.List(
        fields.Nested(_Vulnerability), load_default=list, validate=validate.Length(max=200)
    )


class _Dependencies(Schema):
    packages = fields.List(
        fields.Nested(_Package), required=True, validate=validate.Length(max=5000)
    )


class _SecretFinding(Schema):
    detector = fields.String(required=True, validate=_text)
    path = fields.String(required=True, validate=_text)
    line = fields.Integer(load_default=None, allow_none=True, strict=True)


class _Secrets(Schema):
    count = _counter(required=True)
    findings = fields.List(
        fields.Nested(_SecretFinding), load_default=list, validate=validate.Length(max=1000)
    )

    @validates_schema
    def _count_covers_findings(self, data: dict, **_: object) -> None:
        if data["count"] < len(data["findings"]):
            raise ValidationError("must be at least the number of findings", "count")


class _SastCounts(Schema):
    critical = _counter(required=True)
    high = _counter(required=True)
    medium = _counter(required=True)
    low = _counter(required=True)


class _Sast(Schema):
    new = fields.Nested(_SastCounts, required=True)
    total = fields.Nested(_SastCounts, load_default=None, allow_none=True)


class _Tests(Schema):
    passed = _counter(required=True)
    failed = _counter(required=True)
    skipped = _counter(required=True)


class _Signing(Schema):
    signed = fields.Boolean(required=True, truthy={True}, falsy={False})
    verified = fields.Boolean(required=True, truthy={True}, falsy={False})
    key_id = fields.String(load_default=None, allow_none=True, validate=_text)


class _Evidence(Schema):
    dependencies = fields.Nested(_Dependencies)
    secrets = fields.Nested(_Secrets)
    sast = fields.Nested(_Sast)
    tests = fields.Nested(_Tests)
    signing = fields.Nested(_Signing)


class DryRunSchema(Schema):
    service = fields.String(required=True, validate=validate.Length(min=1, max=64))
    branch = fields.String(required=True, validate=_text)
    environment = fields.String(required=True, validate=validate.OneOf(ENVIRONMENTS))
    version = fields.String(load_default=None, allow_none=True, validate=validate.Length(max=64))
    evidence = fields.Nested(_Evidence, load_default=dict)
    source = fields.String(
        load_default=None, allow_none=True, validate=validate.Length(min=1, max=MAX_SOURCE_BYTES)
    )


class PolicySchema(Schema):
    id = fields.Integer()
    team = fields.String()
    version = fields.Integer()
    active = fields.Boolean()
    comment = fields.String(allow_none=True)
    created_by = fields.String()
    created_at = fields.DateTime()
    source = fields.String()
    warnings = fields.List(fields.String())  # only in the publish response


class ReasonSchema(Schema):
    rule = fields.String()
    outcome = fields.String()
    message = fields.String()
    waiver_id = fields.Integer(allow_none=True)
    details = fields.Dict()


class DryRunResultSchema(Schema):
    decision = fields.String()
    policy_version = fields.Integer(allow_none=True)
    draft = fields.Boolean()
    reasons = fields.List(fields.Nested(ReasonSchema))
    results = fields.List(fields.Nested(ReasonSchema))
