"""Request and response schemas of the waiver routes."""

from __future__ import annotations

from marshmallow import Schema, ValidationError, fields, validate, validates

from gatekeeper.waivers.matching import RULE_ALIASES, RULE_IDS
from gatekeeper.waivers.versions import parse_range


class WaiverRequestSchema(Schema):
    service = fields.String(load_default=None, validate=validate.Length(1, 64))
    rule = fields.String(required=True, validate=validate.OneOf(RULE_IDS + tuple(RULE_ALIASES)))
    version_range = fields.String(load_default=None, validate=validate.Length(1, 128))
    reason = fields.String(required=True, validate=validate.Length(10, 2000))
    expires_at = fields.AwareDateTime(required=True)

    @validates("version_range")
    def _valid_range(self, value: str | None) -> None:
        if value is None:
            return
        try:
            parse_range(value)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc


class ReviewSchema(Schema):
    note = fields.String(load_default=None, validate=validate.Length(1, 2000))


class RejectSchema(Schema):
    note = fields.String(required=True, validate=validate.Length(1, 2000))


class WaiverSchema(Schema):
    id = fields.Integer()
    team = fields.String()
    service = fields.String(allow_none=True)
    rule = fields.String()
    version_range = fields.String(allow_none=True)
    reason = fields.String()
    requested_by = fields.String()
    status = fields.String()
    reviewed_by = fields.String(allow_none=True)
    reviewed_at = fields.DateTime(allow_none=True)
    review_note = fields.String(allow_none=True)
    expires_at = fields.DateTime()
    expiry_notice_sent_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime()
