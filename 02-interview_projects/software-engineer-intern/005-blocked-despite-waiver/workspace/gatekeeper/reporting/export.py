"""CSV export of evaluations (one row per evaluation, oldest first)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Any

COLUMNS = (
    "id", "created_at", "team", "service", "source", "pipeline_id", "commit_sha", "branch",
    "environment", "version", "decision", "policy_version", "rules", "waiver_ids",
)
# Spreadsheets run cells starting with these as formulas (branch names come from CI).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


def to_record(row: Any) -> list[str]:
    reasons = row.reasons or []
    values = {
        **row._mapping,
        "created_at": row.created_at.isoformat(),
        "rules": ";".join(r["rule"] for r in reasons),
        "waiver_ids": ";".join(str(r["waiver_id"]) for r in reasons if r.get("waiver_id")),
    }
    return [_cell(values[c]) for c in COLUMNS]


def render_csv(rows: Iterable[Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(to_record(row))
    return buffer.getvalue()
