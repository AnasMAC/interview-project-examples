from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select, text

from gatekeeper.core.tables import scheduler_runs, waivers
from gatekeeper.scheduler.runner import SCHEDULER_LOCK_ID, Scheduler
from tests.factories import TODAY


@pytest.mark.committed
def test_only_the_lock_holder_runs_jobs(committed_engine):
    ran = []
    first = Scheduler(committed_engine, jobs=[("probe", lambda: ran.append("first") or 1)])
    second = Scheduler(committed_engine, jobs=[("probe", lambda: ran.append("second") or 1)])
    try:
        assert first.tick() is True
        assert second.tick() is False
        # The jobs' own transactions have committed; the session lock is still held.
        assert first.tick() is True and second.tick() is False
        assert ran == ["first", "first"]

        first.release()
        assert second.tick() is True and first.tick() is False
        assert ran == ["first", "first", "second"]
    finally:
        first.release()
        second.release()
    with committed_engine.connect() as conn:
        assert conn.execute(select(scheduler_runs.c.runs, scheduler_runs.c.last_status)).one() == (
            3, "ok")
        # Advisory locks are per database: the dev stack's scheduler may hold its own.
        held = conn.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = :id AND "
            "database = (SELECT oid FROM pg_database WHERE datname = current_database())"
        ), {"id": SCHEDULER_LOCK_ID}).scalar()
    assert held == 0


def test_a_failing_job_is_recorded_and_the_others_still_run(conn, factory, engine):
    waiver = factory.waiver(expires_at=TODAY - timedelta(minutes=5))

    def broken() -> int:
        raise RuntimeError("smtp relay unreachable")

    scheduler = Scheduler(engine, jobs=[("broken", broken), *Scheduler(engine).jobs])
    try:
        assert scheduler.tick() is True
    finally:
        scheduler.release()

    runs = {r.job: r for r in conn.execute(select(scheduler_runs)).all()}
    assert runs["broken"].last_status == "error"
    assert runs["broken"].last_error == "RuntimeError: smtp relay unreachable"
    assert {job: r.last_status for job, r in runs.items() if job != "broken"} == {
        "expire_waivers": "ok", "send_expiry_notices": "ok", "deliver_callbacks": "ok"}
    status = conn.execute(select(waivers.c.status).where(waivers.c.id == waiver.id)).scalar()
    assert status == "expired"
