"""The ``jobs`` table as a queue.

Life of a job: ``queued`` -> ``running`` (``claim``) -> ``done`` (``complete``),
or -> ``failed`` (retried at ``run_after``) / ``dead`` (``fail``). Several
workers can poll at once: ``claim`` locks the row it takes with ``FOR UPDATE
SKIP LOCKED``, so each job goes to exactly one of them.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction

from atlas.core import clock
from atlas.core.logging import redact
from atlas.core.models import Org
from atlas.jobs.models import Job

MAX_ERROR_LENGTH = 4000


def enqueue(org: Org, kind: str, payload: dict, *, run_after: datetime | None = None,
            max_attempts: int | None = None) -> Job:
    from atlas.jobs.handlers import HANDLERS

    if kind not in HANDLERS:
        raise ValueError(f"unknown job kind {kind!r}")
    return Job.objects.create(
        org=org, kind=kind, payload=payload, status=Job.Status.QUEUED,
        run_after=run_after or clock.now(),
        max_attempts=max_attempts or settings.ATLAS_JOB_MAX_ATTEMPTS,
    )


def claim(worker_id: str) -> Job | None:
    """Take the next due job, mark it ``running`` and commit straight away."""
    now = clock.now()
    with transaction.atomic():
        job = (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status__in=[Job.Status.QUEUED, Job.Status.FAILED], run_after__lte=now)
            .order_by("run_after", "id")
            .first()
        )
        if job is None:
            return None
        job.status = Job.Status.RUNNING
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_at = now
        job.save(update_fields=["status", "attempts", "locked_by", "locked_at"])
    return job


def complete(job: Job, result: dict) -> None:
    """Mark ``job`` done; runs in the handler's transaction so both commit together."""
    job.status = Job.Status.DONE
    job.result = result
    job.last_error = ""
    job.locked_by = ""
    job.finished_at = clock.now()
    job.save(update_fields=["status", "result", "last_error", "locked_by", "finished_at"])


def fail(job: Job, error: str, *, permanent: bool = False) -> None:
    """Record a failed attempt in its own transaction (the handler's rolled back)."""
    now = clock.now()
    job.last_error = redact(error)[:MAX_ERROR_LENGTH]
    job.locked_by = ""
    job.result = None
    if permanent or job.attempts >= job.max_attempts:
        job.status = Job.Status.DEAD
        job.finished_at = now
    else:
        job.status = Job.Status.FAILED
        job.run_after = now + timedelta(seconds=backoff_seconds(job.attempts))
    with transaction.atomic():
        job.save(update_fields=["status", "last_error", "locked_by", "result", "finished_at", "run_after"])


def backoff_seconds(attempts: int) -> int:
    return min(10 * 2 ** (max(attempts, 1) - 1), 600)
