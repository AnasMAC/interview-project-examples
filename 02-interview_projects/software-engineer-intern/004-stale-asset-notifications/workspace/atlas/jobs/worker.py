"""The ``run_worker`` loop: one job per iteration, then due webhook deliveries."""

from __future__ import annotations

import threading
import time

from django.db import DatabaseError, close_old_connections, transaction

from atlas.core.logging import get_logger
from atlas.jobs.handlers import HANDLERS, permanent_errors
from atlas.jobs.models import Job
from atlas.jobs.queue import claim, complete, fail

logger = get_logger(__name__)


def run_once(worker_id: str) -> bool:
    """Run at most one job and pump the webhook outbox; True if a job ran."""
    job = claim(worker_id)
    if job is not None:
        execute(job)
    _deliver()
    return job is not None


def execute(job: Job) -> None:
    handler = HANDLERS.get(job.kind)
    context = {"job_id": job.id, "kind": job.kind, "org_id": job.org_id, "attempt": job.attempts}
    if handler is None:
        fail(job, f"no handler for job kind {job.kind!r}", permanent=True)
        logger.error("job.dead", extra=context)
        return
    started = time.monotonic()
    try:
        with transaction.atomic():
            result = handler(job)
            complete(job, result)
    except Exception as error:  # every failure, expected or not, is recorded on the job
        permanent = isinstance(error, permanent_errors())
        fail(job, f"{type(error).__name__}: {error}", permanent=permanent)
        level = logger.error if job.status == Job.Status.DEAD else logger.warning
        level(f"job.{job.status}", extra=context | {"error": job.last_error}, exc_info=not permanent)
        return
    logger.info("job.done", extra=context | {"duration_ms": round((time.monotonic() - started) * 1000)})


def _deliver() -> None:
    from atlas.notify.delivery import deliver_due

    try:
        deliver_due()
    except DatabaseError:
        logger.exception("webhook.deliver_due_failed")


def run_forever(worker_id: str, *, poll_seconds: float, stop: threading.Event | None = None) -> None:
    """Loop until ``stop`` is set; sleeps ``poll_seconds`` when the queue is empty."""
    stop = stop or threading.Event()
    logger.info("worker.started", extra={"worker_id": worker_id, "poll_seconds": poll_seconds})
    while not stop.is_set():
        close_old_connections()  # long-lived process: drop broken or expired connections
        try:
            ran = run_once(worker_id)
        except DatabaseError:
            logger.exception("worker.database_error", extra={"worker_id": worker_id})
            ran = False
        if not ran:
            stop.wait(poll_seconds)
    logger.info("worker.stopped", extra={"worker_id": worker_id})
