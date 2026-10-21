"""Single-runner scheduler loop (docs/architecture.md, "Scheduler").

The process takes the session-level advisory lock ``SCHEDULER_LOCK_ID`` on a
dedicated AUTOCOMMIT connection and keeps it for its whole life; only the
holder runs jobs. A transaction-level lock (``pg_advisory_xact_lock``) would
be released after the first job and let a second instance in. A standby
instance retries every interval and takes over when the holder's session
ends. Each job runs in its own transaction and its outcome is recorded in
``scheduler_runs``; a failing job never stops the others or the loop.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence

from sqlalchemy import Connection, Engine, text
from sqlalchemy.dialects.postgresql import insert

from gatekeeper.core import clock
from gatekeeper.core.db import get_engine, transaction
from gatekeeper.core.logging import get_logger
from gatekeeper.core.tables import scheduler_runs
from gatekeeper.scheduler.jobs import JOBS

log = get_logger(__name__)

SCHEDULER_LOCK_ID = 4150212
MAX_ERROR_LENGTH = 1000


class Scheduler:
    def __init__(
        self,
        engine: Engine | None = None,
        jobs: Sequence[tuple[str, Callable[[], int]]] = JOBS,
    ) -> None:
        self.engine = engine or get_engine()
        self.jobs = jobs
        self._lock_conn: Connection | None = None

    @property
    def is_leader(self) -> bool:
        return self._lock_conn is not None

    def try_acquire(self) -> bool:
        """Hold the lock (or keep holding it); False while another session has it."""
        if self._lock_conn is not None:
            try:
                self._lock_conn.execute(text("SELECT 1"))
                return True
            except Exception:  # noqa: BLE001 - a dead session has lost the lock
                log.error("scheduler.lock_lost", exc_info=True)
                self._lock_conn.invalidate()
                self._lock_conn = None
        conn = self.engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired = conn.execute(
            text("SELECT pg_try_advisory_lock(:id)"), {"id": SCHEDULER_LOCK_ID}
        ).scalar()
        if not acquired:
            conn.close()
            return False
        self._lock_conn = conn
        log.info("scheduler.lock_acquired", extra={"lock_id": SCHEDULER_LOCK_ID})
        return True

    def release(self) -> None:
        if self._lock_conn is None:
            return
        try:
            self._lock_conn.execute(
                text("SELECT pg_advisory_unlock(:id)"), {"id": SCHEDULER_LOCK_ID}
            )
        finally:
            self._lock_conn.close()
            self._lock_conn = None
        log.info("scheduler.lock_released", extra={"lock_id": SCHEDULER_LOCK_ID})

    def tick(self) -> bool:
        """Run every job once if this instance holds the lock; False on standby."""
        if not self.try_acquire():
            log.info("scheduler.standby", extra={"lock_id": SCHEDULER_LOCK_ID})
            return False
        for name, job in self.jobs:
            self.run_job(name, job)
        return True

    def run_job(self, name: str, job: Callable[[], int]) -> None:
        started = clock.now()
        error = None
        try:
            result = job()
        except Exception as exc:  # noqa: BLE001 - recorded, then the next job runs
            error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
            log.exception("scheduler.job_failed", extra={"job": name})
        else:
            log.info("scheduler.job_finished", extra={"job": name, "result": result})
        values = {
            "last_started_at": started,
            "last_finished_at": clock.now(),
            "last_status": "ok" if error is None else "error",
            "last_error": error,
        }
        with transaction() as conn:
            stmt = insert(scheduler_runs).values(job=name, runs=1, **values)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=[scheduler_runs.c.job],
                set_={**values, "runs": scheduler_runs.c.runs + 1},
            ))

    def run_forever(self, stop: threading.Event, interval_s: int) -> None:
        log.info("scheduler.started", extra={"interval_s": interval_s})
        try:
            while not stop.is_set():
                try:
                    self.tick()
                except Exception:  # noqa: BLE001 - e.g. database restarting; try again later
                    log.exception("scheduler.tick_failed")
                stop.wait(interval_s)
        finally:
            self.release()
            log.info("scheduler.stopped")
