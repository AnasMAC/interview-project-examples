"""Open, refresh and resolve Exposure rows from the rule hits.

Runs in the caller's transaction, never commits, and is idempotent: one open
exposure per (asset, rule, subject) (partial unique constraint), refreshed in
place while hit; a hit after a resolve opens a new row, keeping the history.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import batched

from django.db.models import Prefetch

from atlas.assets.models import Asset, AssetChange, AssetLink
from atlas.core.logging import get_logger
from atlas.core.models import Org
from atlas.exposure.models import Exposure
from atlas.exposure.rules import RULES, Hit, RuleContext
from atlas.jobs.models import Job

logger = get_logger(__name__)
CHUNK = 500


@dataclass
class EvaluationResult:
    opened: list[Exposure] = field(default_factory=list)
    resolved: list[Exposure] = field(default_factory=list)
    changes: list[AssetChange] = field(default_factory=list)
    evaluated: int = 0  # assets looked at


def _assets(org: Org, ids: tuple[int, ...]):
    # Rules read services, CNAME links and the links of their targets; fetch
    # them per chunk so a 40k-asset org stays at a handful of queries.
    target_links = Prefetch("target__links_out", AssetLink.objects.only("id", "asset", "relation"))
    links = Prefetch("links_out", AssetLink.objects.select_related("target").prefetch_related(target_links))
    return Asset.objects.for_org(org).filter(id__in=ids).prefetch_related("services", links).order_by("id")


def _hits(asset: Asset, ctx: RuleContext) -> dict[tuple[str, str], Hit]:
    if asset.archived_at is not None:
        return {}  # archived assets keep no open exposures
    return {(rule, hit.subject): hit for rule, check in RULES.items() for hit in check(asset, ctx)}


def _change(org: Org, exposure: Exposure, kind: str, job: Job | None, at) -> AssetChange:
    return AssetChange(
        org=org, asset_id=exposure.asset_id, kind=kind, field=exposure.rule, job=job, occurred_at=at,
        new_value={"exposure_id": exposure.id, "subject": exposure.subject, "severity": exposure.severity},
    )


def evaluate_assets(
    org: Org, asset_ids: Iterable[int] | None = None, *, job: Job | None = None
) -> EvaluationResult:
    ctx = RuleContext.for_org(org)
    if asset_ids is None:
        ids = list(Asset.objects.for_org(org).order_by("id").values_list("id", flat=True))
    else:
        ids = sorted(set(asset_ids))
    result = EvaluationResult()
    for chunk in batched(ids, CHUNK):
        open_rows: dict[int, dict[tuple[str, str], Exposure]] = defaultdict(dict)
        for exposure in Exposure.objects.for_org(org).filter(asset_id__in=chunk, status="open"):
            open_rows[exposure.asset_id][(exposure.rule, exposure.subject)] = exposure
        refreshed, resolved, created = [], [], []
        for asset in _assets(org, chunk):
            result.evaluated += 1
            hits = _hits(asset, ctx)
            for key, exposure in open_rows.pop(asset.id, {}).items():
                hit = hits.pop(key, None)
                exposure.last_evaluated_at = ctx.now
                if hit is None:
                    exposure.status, exposure.resolved_at = Exposure.Status.RESOLVED, ctx.now
                    resolved.append(exposure)
                else:
                    exposure.severity, exposure.title, exposure.details = hit.severity, hit.title, hit.details
                    refreshed.append(exposure)
            created += [
                Exposure(org=org, asset=asset, rule=rule, subject=subject, severity=hit.severity,
                         title=hit.title, details=hit.details, opened_at=ctx.now, last_evaluated_at=ctx.now)
                for (rule, subject), hit in hits.items()
            ]
        Exposure.objects.bulk_update(refreshed, ["severity", "title", "details", "last_evaluated_at"])
        Exposure.objects.bulk_update(resolved, ["status", "resolved_at", "last_evaluated_at"])
        Exposure.objects.bulk_create(created, batch_size=CHUNK)
        changes = [_change(org, e, AssetChange.Kind.EXPOSURE_OPENED, job, ctx.now) for e in created]
        changes += [_change(org, e, AssetChange.Kind.EXPOSURE_RESOLVED, job, ctx.now) for e in resolved]
        result.changes += AssetChange.objects.bulk_create(changes, batch_size=CHUNK)
        result.opened += created
        result.resolved += resolved
    logger.info("exposure.evaluated", extra={
        "org": org.slug, "job_id": job.id if job else None, "evaluated": result.evaluated,
        "opened": len(result.opened), "resolved": len(result.resolved),
    })
    return result
