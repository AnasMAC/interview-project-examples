from __future__ import annotations

import dataclasses

import pytest
from marshmallow import Schema, fields

from gatekeeper.core.app import create_app
from gatekeeper.core.config import get_settings
from gatekeeper.core.errors import Conflict
from gatekeeper.core.http import load_body, page, page_args
from tests.factories import auth_header


class _Body(Schema):
    service = fields.String(required=True)


@pytest.fixture
def scratch_app(conn):
    """A fresh app with a few routes that exercise the shared plumbing."""
    app = create_app(dataclasses.replace(get_settings(), max_payload_bytes=256))

    @app.post("/v1/_echo")
    def echo():
        return {"body": load_body(_Body()), "page": page([], total=0, limit=10, offset=0)}

    @app.get("/v1/_page")
    def paged():
        return {"limit_offset": list(page_args())}

    @app.get("/v1/_conflict")
    def conflict():
        raise Conflict("idempotency key reused", code="idempotency_conflict", details={"id": 4})

    @app.get("/v1/_boom")
    def boom():
        raise RuntimeError("database password=hunter2 leaked")

    return app


@pytest.fixture
def scratch(scratch_app, factory):
    client = scratch_app.test_client()
    client.environ_base["HTTP_AUTHORIZATION"] = auth_header(factory.team_key())["Authorization"]
    return client


def test_healthz_is_public_and_reports_the_version(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json == {"status": "ok", "version": "3.6.1"}


def test_request_id_is_echoed_or_generated(client):
    assert client.get("/healthz", headers={"X-Request-Id": "fl-run-77"}).headers[
        "X-Request-Id"] == "fl-run-77"
    generated = client.get("/healthz", headers={"X-Request-Id": "bad id <x>"})

    assert len(generated.headers["X-Request-Id"]) == 32


def test_unknown_route_is_a_json_404(client):
    response = client.get("/v1/nothing-here")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"


def test_api_errors_use_the_common_body(scratch):
    response = scratch.get("/v1/_conflict")

    assert response.status_code == 409
    assert response.json == {"error": {"code": "idempotency_conflict",
                                       "message": "idempotency key reused", "details": {"id": 4}}}


def test_body_validation(scratch):
    ok = scratch.post("/v1/_echo", json={"service": "payments-api"})
    missing = scratch.post("/v1/_echo", json={})
    not_json = scratch.post("/v1/_echo", data="service=x", content_type="text/plain")

    assert ok.json == {"body": {"service": "payments-api"},
                       "page": {"data": [], "meta": {"total": 0, "limit": 10, "offset": 0}}}
    assert missing.status_code == 422
    assert missing.json["error"]["details"] == {"service": ["Missing data for required field."]}
    assert not_json.status_code == 400 and not_json.json["error"]["code"] == "invalid_json"


def test_oversized_body_is_413(scratch):
    response = scratch.post("/v1/_echo", json={"service": "x" * 400})

    assert response.status_code == 413
    assert response.json["error"]["code"] == "payload_too_large"


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "limit=ten"])
def test_page_args_rejects_out_of_range_values(scratch, query):
    response = scratch.get(f"/v1/_page?{query}")

    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_pagination"


def test_page_args_defaults(scratch):
    assert scratch.get("/v1/_page").json == {"limit_offset": [50, 0]}
    assert scratch.get("/v1/_page?limit=200&offset=400").json == {"limit_offset": [200, 400]}


def test_unhandled_errors_are_500_without_internals(scratch, caplog):
    response = scratch.get("/v1/_boom")

    assert response.status_code == 500
    assert response.json["error"] == {"code": "internal_error",
                                      "message": "internal server error", "details": {}}
    assert "hunter2" not in response.get_data(as_text=True)
    assert any(r.getMessage() == "request.unhandled_error" for r in caplog.records)
