"""Ingest worker entry point.

Usage::

    python -m app.ingest --spool spool/incoming --once
    python -m app.ingest --spool spool/incoming --limit 5      # for debugging

``--processed`` and ``--failed`` default to the directories from
``BELLPOST_SPOOL_PROCESSED_DIR`` / ``BELLPOST_SPOOL_FAILED_DIR``.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the worker once and print its counters."""
    raise NotImplementedError("app.ingest.__main__.main")


if __name__ == "__main__":
    raise SystemExit(main())
