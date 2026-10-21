"""Idempotency keys for ``POST /v1/evaluations`` (3.1.0).

Within a team, the same key with the same payload (sha256 of canonical JSON)
replays the stored evaluation; the same key with another payload is 409.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import Connection, select

from gatekeeper.core.errors import BadRequest, Conflict
from gatekeeper.core.tables import evaluations

HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replay"
_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_key(raw: str | None) -> str | None:
    """The header value, ``None`` when absent; 400 when malformed."""
    if raw is None:
        return None
    if not _KEY.match(raw):
        raise BadRequest(
            f"{HEADER} must be 1 to 128 characters of [A-Za-z0-9._:-]",
            code="invalid_idempotency_key",
        )
    return raw


def find_replay(conn: Connection, *, team_id: int, key: str, payload_sha256: str) -> int | None:
    """Id of the evaluation stored under ``key`` for this team; 409 if its payload differs."""
    row = conn.execute(
        select(evaluations.c.id, evaluations.c.payload_sha256).where(
            evaluations.c.team_id == team_id, evaluations.c.idempotency_key == key
        )
    ).first()
    if row is None:
        return None
    if row.payload_sha256 != payload_sha256:
        raise Conflict(
            f"{HEADER} {key!r} was already used with a different payload",
            code="idempotency_conflict",
            details={"evaluation_id": row.id},
        )
    return row.id
