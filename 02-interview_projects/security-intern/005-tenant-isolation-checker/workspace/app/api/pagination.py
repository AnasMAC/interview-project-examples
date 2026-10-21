"""Cursor (keyset) pagination for the API list endpoints.

Lists are ordered by ``created_at DESC, id DESC`` and the cursor carries the
``(created_at, id)`` of the last row of the previous page, base64url encoded as
``<iso8601>|<id>``. There is no offset and no total count; ``limit`` defaults
to :data:`DEFAULT_LIMIT` and is capped at :data:`MAX_LIMIT`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Select
from sqlalchemy.orm import Session

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
CURSOR_SEPARATOR = "|"


@dataclass(frozen=True)
class Cursor:
    """The position of the last row of a page."""

    created_at: datetime
    id: int


@dataclass(frozen=True)
class Page:
    """One page of rows plus the cursor for the next one (``None`` at the end)."""

    items: list[Any] = field(default_factory=list)
    next_cursor: str | None = None


def parse_limit(raw: str | None) -> int:
    """Read ``?limit=``; defaults to :data:`DEFAULT_LIMIT`, never above :data:`MAX_LIMIT`."""
    raise NotImplementedError("app.api.pagination.parse_limit")


def encode_cursor(created_at: datetime, row_id: int) -> str:
    """Encode ``(created_at, id)`` as an opaque cursor string."""
    raise NotImplementedError("app.api.pagination.encode_cursor")


def decode_cursor(raw: str) -> Cursor:
    """Decode a cursor; invalid input raises 422 ``validation_failed``."""
    raise NotImplementedError("app.api.pagination.decode_cursor")


def paginate(
    session: Session,
    statement: Select,
    model: type[Any],
    *,
    limit: int,
    cursor: str | None = None,
) -> Page:
    """Return one page of ``statement`` ordered by ``(created_at DESC, id DESC)``.

    ``statement`` is the filtered select the caller already built; ``model`` is
    the mapped class whose ``created_at``/``id`` columns drive the keyset.
    """
    raise NotImplementedError("app.api.pagination.paginate")
