"""Small request/response helpers shared by every blueprint."""

from __future__ import annotations

from typing import Any

from flask import request
from marshmallow import Schema

from gatekeeper.core.errors import BadRequest

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def load_body(schema: Schema) -> Any:
    """Parse the JSON body with ``schema``; marshmallow errors become 422."""
    payload = request.get_json(silent=True)
    if payload is None:
        raise BadRequest("request body must be a JSON document", code="invalid_json")
    return schema.load(payload)


def page_args() -> tuple[int, int]:
    """``limit`` (1..200, default 50) and ``offset`` (>= 0) from the query string."""
    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
        offset = int(request.args.get("offset", 0))
    except ValueError as exc:
        raise BadRequest("limit and offset must be integers", code="invalid_pagination") from exc
    if not 1 <= limit <= MAX_LIMIT or offset < 0:
        raise BadRequest(
            f"limit must be 1..{MAX_LIMIT} and offset >= 0", code="invalid_pagination"
        )
    return limit, offset


def page(items: list[Any], *, total: int, limit: int, offset: int) -> dict[str, Any]:
    return {"data": items, "meta": {"total": total, "limit": limit, "offset": offset}}
