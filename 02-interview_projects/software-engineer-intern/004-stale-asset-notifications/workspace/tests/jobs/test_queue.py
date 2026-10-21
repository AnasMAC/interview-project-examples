import threading
from datetime import timedelta

import pytest
from django.db import connection, transaction

from atlas.jobs.models import Job
from atlas.jobs.queue import backoff_seconds, claim, complete, enqueue, fail
from tests.factories import TODAY, make_job, make_org


@pytest.mark.django_db
def test_enqueue_defaults_and_rejects_unknown_kinds(org, settings):
    settings.ATLAS_JOB_MAX_ATTEMPTS = 3
    job = enqueue(org, "exposure.evaluate", {"asset_ids": None})
    assert (job.status, job.attempts, job.max_attempts, job.run_after) == ("queued", 0, 3, TODAY)
    with pytest.raises(ValueError, match="unknown job kind"):
        enqueue(org, "import.later", {})


@pytest.mark.django_db
def test_claim_takes_the_oldest_due_job(org):
    make_job(org, run_after=TODAY + timedelta(seconds=1))
    for status in ("running", "done", "dead"):
        make_job(org, status=status, run_after=TODAY - timedelta(hours=1))
    retry = make_job(org, status="failed", attempts=1, run_after=TODAY - timedelta(minutes=5))
    newest = make_job(org, run_after=TODAY)

    job = claim("worker-a")
    assert job.pk == retry.pk
    assert (job.status, job.attempts, job.locked_by, job.locked_at) == ("running", 2, "worker-a", TODAY)
    assert claim("worker-a").pk == newest.pk
    assert claim("worker-a") is None


@pytest.mark.django_db(transaction=True)
def test_claim_skips_rows_locked_by_another_worker():
    org = make_org()
    first, second = make_job(org), make_job(org)
    locked, release = threading.Event(), threading.Event()

    def other_worker():
        try:
            with transaction.atomic():
                Job.objects.select_for_update().get(pk=first.pk)
                locked.set()
                release.wait(5)
        finally:
            connection.close()

    thread = threading.Thread(target=other_worker)
    thread.start()
    try:
        assert locked.wait(5)
        claimed = claim("worker-b")
    finally:
        release.set()
        thread.join()
    assert claimed.pk == second.pk
    assert Job.objects.get(pk=first.pk).status == "queued"


@pytest.mark.django_db
def test_complete_records_the_result(org):
    make_job(org)
    job = claim("w")
    complete(job, {"created": 2})
    job.refresh_from_db()
    assert (job.status, job.result, job.finished_at, job.locked_by) == ("done", {"created": 2}, TODAY, "")


@pytest.mark.django_db
def test_fail_retries_with_backoff_then_dies(org):
    job = make_job(org, status="running", attempts=2, max_attempts=3, locked_by="w")
    fail(job, "boom with token=abc123")
    job.refresh_from_db()
    assert (job.status, job.run_after, job.locked_by) == ("failed", TODAY + timedelta(seconds=20), "")
    assert job.last_error == "boom with token=[REDACTED]"

    job.attempts = 3
    fail(job, "boom again")
    job.refresh_from_db()
    assert (job.status, job.finished_at) == ("dead", TODAY)


@pytest.mark.django_db
def test_permanent_failure_dies_on_the_first_attempt(org):
    job = make_job(org, status="running", attempts=1)
    fail(job, "bad payload", permanent=True)
    assert Job.objects.get(pk=job.pk).status == "dead"


@pytest.mark.parametrize(("attempts", "seconds"), [(0, 10), (1, 10), (2, 20), (6, 320), (7, 600), (30, 600)])
def test_backoff_doubles_from_ten_seconds_up_to_ten_minutes(attempts, seconds):
    assert backoff_seconds(attempts) == seconds
