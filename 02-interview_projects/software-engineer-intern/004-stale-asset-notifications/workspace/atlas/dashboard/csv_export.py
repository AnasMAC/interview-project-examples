"""CSV download of the asset list, streamed row by row.

Quillstone has ~40k assets: the rows are read with ``iterator()`` and written
straight to the response instead of being built in memory first.
"""

import csv
from collections.abc import Iterator

from django.db.models import QuerySet

from atlas.core import clock

HEADER = (
    "id",
    "kind",
    "key",
    "label",
    "owner_team",
    "tags",
    "open_exposures",
    "first_seen_at",
    "last_seen_at",
    "archived_at",
)
# Spreadsheet apps evaluate cells starting with these. Labels come from
# certificates and cloud resource names, so they are untrusted.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
CHUNK_SIZE = 2000


class _Echo:
    """File-like object whose write() hands the CSV line back to the caller."""

    def write(self, value: str) -> str:
        return value


def cell(value) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def _timestamp(value) -> str:
    return clock.isoformat(value) if value else ""


def asset_rows(assets: QuerySet) -> Iterator[str]:
    """CSV lines for ``assets`` (annotated with ``open_exposures``), header first."""
    writer = csv.writer(_Echo())
    yield writer.writerow(HEADER)
    for asset in assets.prefetch_related("tags").iterator(chunk_size=CHUNK_SIZE):
        row = (
            asset.id,
            asset.kind,
            asset.key,
            asset.label,
            asset.owner_team,
            " ".join(tag.name for tag in asset.tags.all()),
            asset.open_exposures,
            _timestamp(asset.first_seen_at),
            _timestamp(asset.last_seen_at),
            _timestamp(asset.archived_at),
        )
        yield writer.writerow([cell(value) for value in row])
