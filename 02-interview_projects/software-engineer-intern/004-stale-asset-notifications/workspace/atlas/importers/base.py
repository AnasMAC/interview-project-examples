"""Shared types for importers.

An importer turns the text of one export into an ``ImportBatch``: a flat list
of ``Observation`` rows the merge step folds into assets. Importers are pure
(no database, no clock beyond the ``observed_at`` fallback) so they can be
tested on fixture files alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


class ImportFormatError(ValueError):
    """The whole file is unusable; the import job fails permanently."""


@dataclass(frozen=True)
class ObservedLink:
    relation: str  # AssetLink.Relation value
    kind: str  # Asset.Kind of the target
    value: str  # target identity value (same rules as Observation.value)


@dataclass(frozen=True)
class ObservedService:
    port: int
    protocol: str = "tcp"
    service: str = ""
    product: str = ""
    banner: str = ""


@dataclass(frozen=True)
class Observation:
    kind: str  # Asset.Kind value
    # Normalized: hostname / IP / CIDR via atlas.core.normalize, certificate
    # SHA-256 hex, "nimbus:<account_id>:<resource_id>".
    value: str
    label: str = ""
    attributes: dict = field(default_factory=dict)
    external_id: str = ""
    links: tuple[ObservedLink, ...] = ()
    services: tuple[ObservedService, ...] = ()


@dataclass
class ImportBatch:
    importer: str  # registry name
    source_kind: str  # AssetSource.Kind value
    source_name: str  # e.g. "harborview-bank.example.test zone"
    observed_at: datetime  # from the file when it says, else clock.now()
    observations: list[Observation]
    warnings: list[str] = field(default_factory=list)  # skipped records, human readable


def parse_timestamp(value: object) -> datetime:
    """ISO 8601 (``Z`` or offset) or Unix seconds -> aware UTC.

    Naive ISO strings are read as UTC: every export we accept documents its
    timestamps as UTC, and some writers drop the suffix.
    """
    if isinstance(value, bool):
        raise ValueError(f"not a timestamp: {value!r}")
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError):
            raise ValueError(f"timestamp out of range: {value!r}") from None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"not a timestamp: {value!r}")
    parsed = datetime.fromisoformat(value.strip())
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

