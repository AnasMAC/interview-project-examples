"""Job kinds. A handler does the work in the worker's transaction and returns
``Job.result``; it never commits (the worker commits it with ``complete``)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from django.conf import settings

from atlas.assets.models import Asset
from atlas.core.logging import get_logger
from atlas.jobs.models import Job

logger = get_logger(__name__)

MAX_WARNINGS = 100  # kept in Job.result; the count is in the log


class PermanentJobError(Exception):
    """Retrying cannot help (bad payload, missing file): the job goes ``dead``."""


def resolve_import_path(relative: str) -> Path:
    """``relative`` under ``ATLAS_IMPORT_ROOT``; anything escaping it is refused."""
    root = Path(settings.ATLAS_IMPORT_ROOT).resolve()
    path = (root / relative).resolve()
    if not relative or Path(relative).is_absolute() or not path.is_relative_to(root):
        raise PermanentJobError(f"import path must be relative to the import root: {relative!r}")
    if not path.is_file():
        raise PermanentJobError(f"import file not found: {relative!r}")
    return path


def run_import(job: Job) -> dict:
    from atlas.assets.ownership import apply_ownership
    from atlas.exposure.service import evaluate_assets
    from atlas.importers.registry import get_importer
    from atlas.merge.service import merge_batch
    from atlas.notify.outbox import enqueue, publish_changes

    payload = job.payload
    if not isinstance(payload.get("importer"), str) or not isinstance(payload.get("path"), str):
        raise PermanentJobError("import.run needs string 'importer' and 'path'")
    parse = get_importer(payload["importer"])
    try:
        text = resolve_import_path(payload["path"]).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise PermanentJobError(f"import file is not UTF-8: {error}") from None
    batch = parse(text, source_name=payload.get("source_name") or "")

    org = job.org
    merged = merge_batch(org, batch, job=job)
    owner_changes = apply_ownership(org, merged.touched, job=job)
    evaluation = evaluate_assets(org, merged.touched, job=job)
    events = publish_changes(org, [*merged.changes, *owner_changes, *evaluation.changes])
    summary = {
        "job_id": job.id,
        "importer": payload["importer"],
        "source_name": batch.source_name,
        "created": len(merged.created),
        "updated": len(merged.updated),
        "unchanged": len(merged.unchanged),
        "exposures_opened": len(evaluation.opened),
        "exposures_resolved": len(evaluation.resolved),
    }
    events += enqueue(org, "import.completed", summary)
    # "created" is a LogRecord attribute: logging refuses it as an extra field.
    counts = {f"assets_{key}" if key in ("created", "updated", "unchanged") else key: value
              for key, value in summary.items()}
    logger.info("import.completed", extra={"org": org.slug, "warnings": len(batch.warnings), **counts})
    result = {key: value for key, value in summary.items() if key != "job_id"}
    return result | {"observations": len(batch.observations), "warnings": batch.warnings[:MAX_WARNINGS],
                     "events": len(events)}


def run_exposure_evaluation(job: Job) -> dict:
    from atlas.exposure.service import evaluate_assets
    from atlas.notify.outbox import publish_changes

    asset_ids = job.payload.get("asset_ids")
    if asset_ids is not None and not (
        isinstance(asset_ids, list) and all(type(value) is int for value in asset_ids)
    ):
        raise PermanentJobError("exposure.evaluate needs 'asset_ids': a list of ints or null")
    assets = Asset.objects.for_org(job.org)
    evaluated = (assets if asset_ids is None else assets.filter(id__in=asset_ids)).count()
    evaluation = evaluate_assets(job.org, asset_ids, job=job)
    events = publish_changes(job.org, evaluation.changes)
    return {"evaluated": evaluated, "opened": len(evaluation.opened),
            "resolved": len(evaluation.resolved), "events": len(events)}


HANDLERS: dict[str, Callable[[Job], dict]] = {
    "import.run": run_import,
    "exposure.evaluate": run_exposure_evaluation,
}


def permanent_errors() -> tuple[type[Exception], ...]:
    from atlas.importers.base import ImportFormatError
    from atlas.importers.registry import UnknownImporter

    return (PermanentJobError, ImportFormatError, UnknownImporter)
