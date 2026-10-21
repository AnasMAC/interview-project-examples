import json
import logging

from django.http import Http404
from rest_framework import exceptions

from atlas.core.exceptions import Conflict, api_exception_handler
from atlas.core.logging import JsonFormatter, redact
from atlas.core.normalize import NormalizationError


def _handle(exc):
    response = api_exception_handler(exc, {})
    return response.status_code, response.data["error"], response


def test_validation_errors_keep_field_details():
    status, error, _ = _handle(exceptions.ValidationError({"key": ["This field is required."]}))
    assert status == 400
    assert error == {"code": "validation_failed", "message": "Invalid request.",
                     "details": {"key": ["This field is required."]}}


def test_django_404_and_normalization_errors_are_translated():
    assert _handle(Http404())[:2] == (404, {"code": "not_found", "message": "Not found.", "details": None})
    status, error, _ = _handle(NormalizationError("invalid IP address: 'x'"))
    assert (status, error["code"]) == (400, "validation_failed")


def test_conflict_and_auth_codes():
    assert _handle(Conflict("Tag exists."))[1]["code"] == "conflict"
    assert _handle(exceptions.NotAuthenticated())[:2][0] == 401
    assert _handle(exceptions.AuthenticationFailed("bad"))[1]["code"] == "unauthenticated"


def test_throttled_reports_retry_after():
    status, error, response = _handle(exceptions.Throttled(wait=12.2))
    assert status == 429 and error["code"] == "throttled"
    assert error["details"] == {"retry_after_seconds": 13}
    assert response["Retry-After"] == "13"


def test_unexpected_errors_fall_through_to_django():
    assert api_exception_handler(RuntimeError("boom"), {}) is None


def test_redact_masks_keys_secrets_and_bearer_values():
    text = ("auth Bearer atl_DEMO_abc123 key=atl_DEMO_zz9 secret=DEMO-whsec-harborview-bank-1a2b "
            "url=/hooks?token=t0k3n&x=1")
    assert redact(text) == ("auth Bearer [REDACTED] key=[REDACTED] secret=[REDACTED] "
                            "url=/hooks?token=[REDACTED]&x=1")


def test_json_formatter_includes_extras_and_redacts_secret_fields():
    record = logging.makeLogRecord(
        {"name": "atlas.notify", "levelname": "INFO", "msg": "webhook.sent to %s",
         "args": ("mockhook",), "org": "harborview-bank", "webhook_secret": "DEMO-whsec-x"}
    )
    line = json.loads(JsonFormatter().format(record))
    assert line["event"] == "webhook.sent to mockhook"
    assert line["org"] == "harborview-bank" and line["webhook_secret"] == "[REDACTED]"
