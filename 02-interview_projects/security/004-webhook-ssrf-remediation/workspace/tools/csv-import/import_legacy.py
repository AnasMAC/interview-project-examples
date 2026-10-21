#!/usr/bin/env python3
"""One-off importer for the 2023 helpdesk export (archived).

This script migrated the old Helpdesk 2019 SQLite database into Bellpost in
2023 and has not been touched since; it is kept only because two customer
exports were re-run from it. It is **not part of the product**: nothing in
``app/`` imports it, it has no tests, and it is excluded from the build and
from the review checklist. It reads the export from a local file and writes
into a local SQLite database, so it never touches production data.

Usage::

    python tools/csv-import/import_legacy.py --csv old-helpdesk-export.csv --db legacy.db

Do not extend this script: new imports go through the ticket API.
"""

from __future__ import annotations

import argparse

LEGACY_TABLES = ("hdp_users", "hdp_tickets", "hdp_messages")


def import_rows(csv_path: str, db_path: str) -> tuple[int, int]:
    """Copy users and tickets from the 2023 CSV export into SQLite."""
    raise NotImplementedError("tools.csv-import.import_legacy.import_rows")


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description="One-off importer for the 2023 helpdesk export")
    parser.add_argument("--csv", required=True, help="path to the 2023 CSV export")
    parser.add_argument("--db", required=True, help="path to the SQLite database to write")
    args = parser.parse_args(argv)
    raise NotImplementedError("tools.csv-import.import_legacy.main")


if __name__ == "__main__":
    raise SystemExit(main())
