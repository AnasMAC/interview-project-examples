"""Worker and handlers. Importers, ownership, exposure and notify are faked;
the merge is real."""

import threading
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import CommandError, call_command

from atlas.assets.models import Asset, AssetChange
from atlas.importers.base import ImportBatch, ImportFormatError, Observation, ObservedLink
from atlas.importers.registry import UnknownImporter
from atlas.jobs import worker
from atlas.jobs.models import Job
from atlas.jobs.queue import enqueue
from tests.factories import TODAY, make_asset, make_job

pytestmark = pytest.mark.django_db

WWW = "www.harborview-bank.example.test"
IMPORT = {"importer": "zone_file", "path": "zone/harborview.zone"}


@pytest.fixture
def pipeline(monkeypatch, settings, tmp_path):
    settings.ATLAS_IMPORT_ROOT = tmp_path
    (tmp_path / "zone").mkdir()
    (tmp_path / "zone" / "harborview.zone").write_text("www IN A 198.51.100.7\n")
    calls = SimpleNamespace(parsed=[], ownership=[], evaluated=[], published=[], events=[], deliveries=0)

    def parse(text, *, source_name=""):
        calls.parsed.append((text, source_name))
        www = Observation("host", WWW, links=(ObservedLink("resolves_to", "ip", "198.51.100.7"),))
        return ImportBatch("zone_file", "zone_file", source_name or "harborview zone", TODAY, [www],
                           warnings=["line 7: unsupported record type"])

    def evaluate_assets(org, asset_ids, *, job=None):
        calls.evaluated.append(asset_ids)
        return SimpleNamespace(opened=["exposure"], resolved=[], changes=[])

    def deliver_due():
        calls.deliveries += 1
        return 0

    def outbox_enqueue(org, event, data):
        calls.events.append((event, data))
        return ["row"]

    monkeypatch.setattr("atlas.importers.registry.get_importer", lambda name: parse)
    monkeypatch.setattr("atlas.assets.ownership.apply_ownership",
                        lambda org, ids, *, job=None: calls.ownership.append(list(ids)) or [])
    monkeypatch.setattr("atlas.exposure.service.evaluate_assets", evaluate_assets)
    monkeypatch.setattr("atlas.notify.outbox.publish_changes",
                        lambda org, changes: calls.published.append(list(changes)) or ["row"] * len(changes))
    monkeypatch.setattr("atlas.notify.outbox.enqueue", outbox_enqueue)
    monkeypatch.setattr("atlas.notify.delivery.deliver_due", deliver_due)
    return calls


def test_import_job_runs_the_pipeline_and_commits_with_complete(org, pipeline):
    job = enqueue(org, "import.run", IMPORT | {"source_name": "dns primary"})
    assert worker.run_once("w1") is True

    job.refresh_from_db()
    touched = list(Asset.objects.order_by("id").values_list("id", flat=True))
    assert (job.status, job.attempts, job.finished_at) == ("done", 1, TODAY)
    assert job.result == {
        "importer": "zone_file", "source_name": "dns primary", "observations": 1, "created": 2,
        "updated": 0, "unchanged": 0, "warnings": ["line 7: unsupported record type"],
        "exposures_opened": 1, "exposures_resolved": 0, "events": 4,
    }
    assert pipeline.parsed == [("www IN A 198.51.100.7\n", "dns primary")]
    assert pipeline.ownership == [touched] and pipeline.evaluated == [touched]
    assert pipeline.published == [list(AssetChange.objects.order_by("id"))]
    assert pipeline.events == [("import.completed", {
        "job_id": job.id, "importer": "zone_file", "source_name": "dns primary", "created": 2,
        "updated": 0, "unchanged": 0, "exposures_opened": 1, "exposures_resolved": 0,
    })]
    assert pipeline.deliveries == 1
    assert set(AssetChange.objects.values_list("job_id", flat=True)) == {job.id}


def test_failure_rolls_back_the_import_and_schedules_a_retry(org, pipeline, monkeypatch):
    def explode(org, asset_ids, *, job=None):
        raise RuntimeError("rule table exploded")

    monkeypatch.setattr("atlas.exposure.service.evaluate_assets", explode)
    job = enqueue(org, "import.run", IMPORT)
    worker.run_once("w1")

    job.refresh_from_db()
    assert (job.status, job.attempts, job.run_after) == ("failed", 1, TODAY + timedelta(seconds=10))
    assert job.last_error == "RuntimeError: rule table exploded" and job.result is None
    assert not Asset.objects.exists() and not AssetChange.objects.exists() and pipeline.events == []


def _raise(error):
    def fail(*args, **kwargs):
        raise error
    return fail


@pytest.mark.parametrize(
    ("payload", "get_importer", "error"),
    [
        (IMPORT, lambda name: _raise(ImportFormatError("no SOA")), "ImportFormatError: no SOA"),
        (IMPORT, _raise(UnknownImporter("bind9")), "UnknownImporter"),
        (IMPORT | {"path": "../../etc/passwd"}, None, "must be relative to the import root"),
        (IMPORT | {"path": "/etc/passwd"}, None, "must be relative to the import root"),
        (IMPORT | {"path": "zone/missing.zone"}, None, "import file not found"),
        ({"importer": "zone_file"}, None, "needs string 'importer' and 'path'"),
    ],
)
def test_permanent_errors_kill_the_job_at_once(org, pipeline, monkeypatch, payload, get_importer, error):
    if get_importer is not None:
        monkeypatch.setattr("atlas.importers.registry.get_importer", get_importer)
    job = enqueue(org, "import.run", payload)
    worker.run_once("w1")
    job.refresh_from_db()
    assert (job.status, job.attempts, job.finished_at) == ("dead", 1, TODAY)
    assert error in job.last_error


def test_exposure_evaluate_job(org, pipeline):
    make_asset(org)
    make_asset(org)
    job = enqueue(org, "exposure.evaluate", {"asset_ids": None})
    worker.run_once("w1")

    job.refresh_from_db()
    assert job.result == {"evaluated": 2, "opened": 1, "resolved": 0, "events": 0}
    assert pipeline.evaluated == [None]


def test_invalid_exposure_payload_and_unknown_kind_are_dead(org, pipeline):
    bad = enqueue(org, "exposure.evaluate", {"asset_ids": [1, "2"]})
    stray = make_job(org, kind="report.render", run_after=TODAY + timedelta(seconds=-1))
    worker.run_once("w1")
    worker.run_once("w1")
    assert Job.objects.get(pk=bad.pk).status == Job.objects.get(pk=stray.pk).status == "dead"


def test_idle_iteration_still_delivers_webhooks(pipeline):
    assert worker.run_once("w1") is False
    assert pipeline.deliveries == 1


def test_run_forever_polls_until_stopped(monkeypatch):
    stop, calls = threading.Event(), []

    def run_once(worker_id):
        calls.append(worker_id)
        if len(calls) == 3:
            stop.set()
        return len(calls) == 1

    monkeypatch.setattr(worker, "run_once", run_once)
    worker.run_forever("w9", poll_seconds=0.01, stop=stop)
    assert calls == ["w9"] * 3


def test_enqueue_import_command(org, pipeline):
    out = StringIO()
    call_command("enqueue_import", "--org", org.slug, "--importer", "zone_file",
                 "--path", IMPORT["path"], "--source-name", "dns primary", stdout=out)
    job = Job.objects.get()
    assert (job.kind, job.payload) == ("import.run", IMPORT | {"source_name": "dns primary"})
    assert f"queued job {job.id}" in out.getvalue()

    call_command("run_worker", "--once", "--worker-id", "cli", stdout=out)
    assert Job.objects.get().status == "done" and "ran one job" in out.getvalue()


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--org", "nope", "--importer", "zone_file", "--path", IMPORT["path"]], "unknown org"),
        (["--org", "harborview-bank", "--importer", "bind9", "--path", IMPORT["path"]], "unknown importer"),
        (["--org", "harborview-bank", "--importer", "zone_file", "--path", "../x"], "import root"),
    ],
)
def test_enqueue_import_command_validates(org, pipeline, args, message):
    with pytest.raises(CommandError, match=message):
        call_command("enqueue_import", *args)
    assert not Job.objects.exists()
