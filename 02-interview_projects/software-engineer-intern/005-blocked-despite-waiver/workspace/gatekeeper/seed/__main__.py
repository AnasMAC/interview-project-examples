"""python -m gatekeeper.seed [--seed 7] [--scale 1] [--reset]"""

from __future__ import annotations

import argparse
import sys
import time

from gatekeeper.core.config import get_settings
from gatekeeper.core.db import transaction
from gatekeeper.seed.generate import SeedError, generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gatekeeper.seed", description=__doc__)
    parser.add_argument("--seed", type=int, default=7, help="random seed (default 7)")
    parser.add_argument("--scale", type=float, default=1.0,
                        help="multiply the ~8,000 evaluations (default 1)")
    parser.add_argument("--reset", action="store_true", help="truncate every table first")
    args = parser.parse_args(argv)
    if not 0 < args.scale <= 100:
        parser.error("--scale must be in (0, 100]")
    if args.reset and get_settings().env == "prod":
        parser.error("--reset is refused when GATE_ENV=prod")
    started = time.perf_counter()
    try:
        with transaction() as conn:
            summary = generate(conn, seed=args.seed, scale=args.scale, reset=args.reset)
    except SeedError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 1
    for name, value in summary.items():
        print(f"{name:<16} {value}")
    print(f"seeded in {time.perf_counter() - started:.1f}s (seed {args.seed}, scale {args.scale})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
