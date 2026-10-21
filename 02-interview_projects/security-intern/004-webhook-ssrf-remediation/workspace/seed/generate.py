"""Deterministic demo data generator.

Do not edit by hand: regenerate with ``python seed/generate.py --seed 1``.
(The 2026-04 Cascade Freight patch below was applied directly to keep the
performance fixture at the volume support asked for; fold it back into the
generator when the reporting work lands.)

Usage::

    python seed/generate.py --seed 1
    python seed/generate.py --seed 1 --scale 1.0
    python seed/generate.py --seed 1 --reset      # wipe and reload demo data

Everything is anchored at the fictional today (``ANCHOR``, 2026-05-11 09:00
+01:00) and covers :data:`HISTORY_START` .. :data:`HISTORY_END`. Seed 1
produces:

* 4 tenants, 16 users (4 per tenant: admin, agent, two requesters);
* 2,990 tickets (Cascade Freight 2,400; Brightpath Labs 320; Tidalbrook Water
  180; Hollisvale Legal 90), 9,200 messages;
* 210 attachments with real small files under ``seed/attachments/``;
* 5,600 audit events, 6 webhooks (2 disabled), 1,240 deliveries (12 dead);
* 40 ``.eml`` files in ``spool/incoming`` (2 duplicates, 3 unsupported ``.msg``)
  and 12 ``.eml`` files in ``spool/processed``.

The run ends by printing the demo credentials (``DEMO-<slug>-<role>``,
``DEMO-bpk-<prefix>-<role>-0001``).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

ANCHOR = datetime(2026, 5, 11, 9, 0, tzinfo=ZoneInfo("Europe/London"))
HISTORY_START = date(2026, 2, 2)
HISTORY_END = date(2026, 5, 8)
DEFAULT_SEED = 1

#: hand-edit: Cascade Freight keeps 2,400 tickets for the reporting/perf work.
CDF_TICKETS = 2400

#: ticket volume per tenant slug for ``--scale 1.0``.
TENANT_VOLUMES: dict[str, int] = {
    "brightpath": 320,
    "cascade": CDF_TICKETS,
    "tidalbrook": 180,
    "hollisvale": 90,
}


@dataclass
class SeedReport:
    """Row counts the run created."""

    tenants: int = 0
    users: int = 0
    tickets: int = 0
    messages: int = 0
    attachments: int = 0
    audit_events: int = 0
    webhooks: int = 0
    deliveries: int = 0
    spool_files: int = 0
    processed_files: int = 0
    credentials: list[str] = field(default_factory=list)


def build(
    seed: int = DEFAULT_SEED,
    scale: float = 1.0,
    *,
    reset: bool = False,
    quiet: bool = False,
) -> SeedReport:
    """Generate demo data; refuse to run over existing tenants without ``--reset``."""
    raise NotImplementedError("seed.generate.build")


def main(argv: list[str] | None = None) -> int:
    """Command line entry point."""
    parser = argparse.ArgumentParser(description="Generate Bellpost demo data")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="deterministic seed (default 1)")
    parser.add_argument("--scale", type=float, default=1.0, help="volume multiplier (default 1.0)")
    parser.add_argument("--reset", action="store_true", help="delete existing demo tenants first")
    parser.add_argument("--quiet", action="store_true", help="only print the demo credentials")
    args = parser.parse_args(argv)
    raise NotImplementedError("seed.generate.main")


if __name__ == "__main__":
    raise SystemExit(main())
