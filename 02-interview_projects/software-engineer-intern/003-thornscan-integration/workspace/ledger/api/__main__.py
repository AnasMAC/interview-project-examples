"""``python3 -m ledger.api``: serve the JSON API on ``Settings.api_host:api_port`` until interrupted."""

from __future__ import annotations

import contextlib
import sys

from ledger.api.server import make_server
from ledger.core import clock, db, log, migrations
from ledger.core.config import get_settings
from ledger.core.errors import LedgerError


def main() -> int:
    try:
        settings = get_settings()
    except LedgerError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 2
    log.configure(settings.log_level, settings.log_format)
    if settings.now is not None:
        clock.use(lambda: settings.now)
    logger = log.get_logger("api")
    with contextlib.closing(db.open_db(settings)) as conn:
        if migrations.pending(conn):
            logger.warning("api.pending_migrations", extra={"hint": "run python3 -m ledger migrate"})
    server = make_server(settings)
    host, port = server.server_address[:2]
    logger.info("api.listening", extra={"url": f"http://{host}:{port}", "db": str(settings.db_path)})
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("api.stopping")
    finally:
        server.server_close()
    return 0


raise SystemExit(main())
