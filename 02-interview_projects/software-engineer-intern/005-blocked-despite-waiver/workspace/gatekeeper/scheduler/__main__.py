"""``python -m gatekeeper.scheduler [--once]``."""

from __future__ import annotations

import argparse
import signal
import sys
import threading

from gatekeeper.core.config import get_settings
from gatekeeper.core.logging import configure_logging, get_logger
from gatekeeper.scheduler.runner import Scheduler

log = get_logger("gatekeeper.scheduler")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m gatekeeper.scheduler")
    parser.add_argument("--once", action="store_true",
                        help="run every job once and exit (1 if another scheduler holds the lock)")
    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format, settings.service_name)
    scheduler = Scheduler()
    if args.once:
        try:
            if not scheduler.tick():
                log.error("scheduler.lock_held")
                return 1
            return 0
        finally:
            scheduler.release()
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    scheduler.run_forever(stop, settings.scheduler_interval_s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
