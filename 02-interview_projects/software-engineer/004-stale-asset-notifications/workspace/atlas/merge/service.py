"""Fold an ``ImportBatch`` into the org's inventory.

Rules (docs/architecture.md §4.4, ADR 0002 as amended in 0.12):

* one asset per ``(org, kind, identity_key)``; one ``AssetSource`` per
  ``(asset, source_kind, source_name)``;
* ``first_seen_at`` keeps the minimum and ``last_seen_at`` the maximum of the
  batches' ``observed_at`` (on assets, sources, links and services);
* label and attributes come from the most recently seen source: a batch
  older than the asset's ``last_seen_at`` adds provenance but never rewrites
  them (re-importing an old snapshot does not roll the inventory back).
  Attributes are merged key by key, an empty label keeps the current one;
* link targets are assets too: created when missing, with this source as
  provenance;
* a ``port_scan`` batch closes the open services it no longer reports on
  the assets it scanned: its ``ip`` observations (an up address with no open
  port closes everything) and any asset it reports services for; ``host``
  observations only name a target and close nothing. A newer scan wins;
* an archived asset seen again by a batch at least as new as the archive is
  restored;
* a hostname is one asset across ``domain`` and ``host`` (``identity_kinds``):
  a ``host`` observation or link target reuses an existing ``domain`` of the
  same name, and a direct ``domain`` observation (the zone apex) turns an
  existing ``host`` into a ``domain`` (an ``updated`` change, ``field`` =
  ``"kind"``), so the CT feed's apex SAN never duplicates the zone apex,
  whichever is imported first.

Every difference is one ``AssetChange`` carrying ``job``; re-importing the
same snapshot writes none. Runs inside the caller's transaction and takes a
row lock on the org, so two imports for one org merge one after the other.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from atlas.assets.models import Asset, AssetChange, AssetLink, AssetService, AssetSource
from atlas.core import clock
from atlas.core.logging import get_logger
from atlas.core.models import Org
from atlas.core.normalize import NormalizationError
from atlas.merge.certificates import candidate_hosts, candidate_sans, covered_names, hostname_matches
from atlas.merge.identity import default_attributes, identity_key, identity_kinds

logger = get_logger(__name__)

Kind = AssetChange.Kind
NAMED = (Asset.Kind.HOST, Asset.Kind.DOMAIN)  # what a certificate SAN can cover (the apex is a domain)


@dataclass
class MergeResult:
    created: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    unchanged: list[int] = field(default_factory=list)
    changes: list[AssetChange] = field(default_factory=list)

    @property
    def touched(self) -> list[int]:
        return [*self.created, *self.updated, *self.unchanged]


def merge_batch(org: Org, batch, *, job=None) -> MergeResult:
    """``batch`` is an ``atlas.importers.base.ImportBatch``. Invalid values are
    skipped and reported in ``batch.warnings``."""
    Org.objects.select_for_update().only("pk").get(pk=org.pk)
    return _Merge(org, batch, job).run()


class _Merge:
    def __init__(self, org: Org, batch, job) -> None:
        self.org, self.batch, self.job = org, batch, job
        self.at = batch.observed_at
        self.assets: dict[tuple[str, str], Asset] = {}
        self.by_id: dict[int, Asset] = {}
        self.status: dict[int, str] = {}  # asset id -> created / updated / unchanged, first-seen order
        self.sources: dict[int, AssetSource] = {}
        self.dirty_assets: set[int] = set()
        self.dirty_sources: set[int] = set()
        self.scanned: set[int] = set()  # assets observed directly, not only as a link target
        self.probed: set[int] = set()  # port_scan targets whose unreported services close
        self.links: dict[tuple[int, int, str], None] = {}
        self.services: dict[int, dict[tuple[int, str], object]] = defaultdict(dict)
        self.changes: list[AssetChange] = []

    def run(self) -> MergeResult:
        observations = self._identify()
        self._load(observations)
        for kind, key, obs, links in observations:
            asset = self._observe(kind, key, obs.label, obs.attributes, obs.external_id, direct=True)
            self.scanned.add(asset.id)
            if kind == Asset.Kind.IP or obs.services:
                self.probed.add(asset.id)
            for service in obs.services:
                self.services[asset.id][(service.port, service.protocol.lower())] = service
            for relation, target_kind, target_key in links:
                target = self._observe(target_kind, target_key, "", {}, "", direct=False)
                self.links[(asset.id, target.id, relation)] = None
        self._certificate_links()
        self._save_links()
        self._save_services()
        self._flush()
        result = MergeResult(changes=self.changes)
        for asset_id, status in self.status.items():
            getattr(result, status).append(asset_id)
        logger.info(
            "merge.completed",
            extra={"org": self.org.slug, "source_name": self.batch.source_name,
                   "assets_created": len(result.created), "assets_updated": len(result.updated),
                   "assets_unchanged": len(result.unchanged)},
        )
        return result

    # --- identities -----------------------------------------------------------

    def _identify(self) -> list[tuple[str, str, object, list[tuple[str, str, str]]]]:
        identified = []
        for obs in self.batch.observations:
            try:
                key = identity_key(obs.kind, obs.value)
            except NormalizationError as error:
                self.batch.warnings.append(f"skipped {obs.kind} {obs.value!r}: {error}")
                continue
            links = []
            for link in obs.links:
                try:
                    links.append((link.relation, link.kind, identity_key(link.kind, link.value)))
                except NormalizationError as error:
                    self.batch.warnings.append(f"skipped {link.relation} link of {key}: {error}")
            identified.append((obs.kind, key, obs, links))
        return identified

    def _load(self, observations) -> None:
        wanted: dict[str, set[str]] = defaultdict(set)
        for kind, key, _, links in observations:
            wanted[kind].add(key)
            for _, target_kind, target_key in links:
                wanted[target_kind].add(target_key)
        names = wanted.pop(Asset.Kind.HOST, set()) | wanted.pop(Asset.Kind.DOMAIN, set())
        if names:
            wanted[Asset.Kind.HOST] = names
        for kind, keys in wanted.items():
            for asset in Asset.objects.for_org(self.org).filter(kind__in=identity_kinds(kind), key__in=keys):
                self._remember(asset)
        sources = AssetSource.objects.for_org(self.org).filter(
            asset_id__in=list(self.by_id),
            source_kind=self.batch.source_kind,
            source_name=self.batch.source_name,
        )
        self.sources = {source.asset_id: source for source in sources}

    def _remember(self, asset: Asset) -> None:
        self.assets[(asset.kind, asset.key)] = asset
        self.by_id[asset.id] = asset

    def _find(self, kind: str, key: str) -> Asset | None:
        for candidate in identity_kinds(kind):
            if (asset := self.assets.get((candidate, key))) is not None:
                return asset
        return None

    # --- assets and provenance ------------------------------------------------

    def _observe(self, kind, key, label, attributes, external_id, *, direct: bool) -> Asset:
        label = label[:512]
        asset = self._find(kind, key)
        if asset is None:
            asset = Asset.objects.create(
                org=self.org, kind=kind, key=key, label=label or key,
                attributes=default_attributes(kind, key) | attributes,
                first_seen_at=self.at, last_seen_at=self.at,
            )
            self._remember(asset)
            self.status[asset.id] = "created"
            self._change(asset, Kind.CREATED, new={"key": key, "label": asset.label,
                                                   "source_name": self.batch.source_name})
        else:
            self.status.setdefault(asset.id, "unchanged")
            if direct and kind == Asset.Kind.DOMAIN and asset.kind == Asset.Kind.HOST:
                self._change(asset, Kind.UPDATED, "kind", asset.kind, kind)
                del self.assets[(asset.kind, key)]
                asset.kind = kind
                self._remember(asset)
            self._refresh(asset, label, attributes)
        self._provenance(asset, attributes, external_id, direct=direct)
        return asset

    def _refresh(self, asset: Asset, label: str, attributes: dict) -> None:
        if asset.archived_at is not None and self.at >= asset.archived_at:
            self._change(asset, Kind.UPDATED, "archived_at", clock.isoformat(asset.archived_at), None)
            asset.archived_at = None
        if self.at >= asset.last_seen_at:
            if label and label != asset.label:
                self._change(asset, Kind.UPDATED, "label", asset.label, label)
                asset.label = label
            merged = asset.attributes | attributes
            if merged != asset.attributes:
                self._change(asset, Kind.UPDATED, "attributes", asset.attributes, merged)
                asset.attributes = merged
        if self._widen(asset):
            self.dirty_assets.add(asset.id)

    def _provenance(self, asset: Asset, attributes: dict, external_id: str, *, direct: bool) -> None:
        source = self.sources.get(asset.id)
        if source is None:
            self.sources[asset.id] = AssetSource.objects.create(
                asset=asset, source_kind=self.batch.source_kind, source_name=self.batch.source_name,
                external_id=external_id, raw=attributes, first_seen_at=self.at, last_seen_at=self.at,
            )
            if self.status[asset.id] != "created":
                self._change(asset, Kind.SOURCE_ADDED, self.batch.source_kind, None, self.batch.source_name)
            return
        before = (source.raw, source.external_id)
        if direct and self.at >= source.last_seen_at:
            source.raw = attributes
            source.external_id = external_id or source.external_id
        if self._widen(source) or (source.raw, source.external_id) != before:
            self.dirty_sources.add(asset.id)

    # --- links ----------------------------------------------------------------

    def _certificate_links(self) -> None:
        """``covers`` links both ways: certificates in this batch -> the org's
        hosts and domains, and the org's certificates -> those created by this
        batch. Links an importer already emitted are the same dict key."""
        hosts = Asset.objects.for_org(self.org).filter(kind__in=NAMED)
        for asset in list(self.by_id.values()):
            if asset.kind != Asset.Kind.CERTIFICATE or asset.id not in self.scanned:
                continue
            names = covered_names(asset.attributes)
            query = candidate_hosts(names)
            if query is None:
                continue
            for host in hosts.filter(query).only("id", "key"):
                if any(hostname_matches(name, host.key) for name in names):
                    self.links[(asset.id, host.id, AssetLink.Relation.COVERS)] = None

        created = [
            a for a in self.by_id.values() if a.kind in NAMED and self.status[a.id] == "created"
        ]
        if not created:
            return
        names = sorted({name for host in created for name in candidate_sans(host.key)})
        certificates = Asset.objects.for_org(self.org).filter(
            kind=Asset.Kind.CERTIFICATE, attributes__sans__has_any_keys=names
        )
        for certificate in certificates.only("id", "attributes"):
            sans = covered_names(certificate.attributes)
            for host in created:
                if any(hostname_matches(name, host.key) for name in sans):
                    self.links[(certificate.id, host.id, AssetLink.Relation.COVERS)] = None

    def _save_links(self) -> None:
        if not self.links:
            return
        sources = {asset_id for asset_id, _, _ in self.links}
        links = AssetLink.objects.for_org(self.org).filter(asset_id__in=sources)
        existing = {(link.asset_id, link.target_id, link.relation): link for link in links}
        new, dirty = [], []
        for asset_id, target_id, relation in self.links:
            link = existing.get((asset_id, target_id, relation))
            if link is None:
                new.append(AssetLink(asset_id=asset_id, target_id=target_id, relation=relation,
                                     source_kind=self.batch.source_kind,
                                     first_seen_at=self.at, last_seen_at=self.at))
                asset = self._asset(asset_id)
                self._change(asset, Kind.LINK_ADDED, relation, None, self._asset(target_id).key)
            elif self._widen(link):
                dirty.append(link)
        AssetLink.objects.bulk_create(new)
        AssetLink.objects.bulk_update(dirty, ["first_seen_at", "last_seen_at"])

    def _asset(self, asset_id: int) -> Asset:
        if asset_id not in self.by_id:  # an existing certificate covering a new host
            self._remember(Asset.objects.for_org(self.org).get(pk=asset_id))
            self.status.setdefault(asset_id, "unchanged")
        return self.by_id[asset_id]

    # --- services -------------------------------------------------------------

    def _save_services(self) -> None:
        closing = self.batch.source_kind == AssetSource.Kind.PORT_SCAN
        asset_ids = set(self.services) | (self.probed if closing else set())
        if not asset_ids:
            return
        services = AssetService.objects.for_org(self.org).filter(asset_id__in=asset_ids)
        existing = {(s.asset_id, s.port, s.protocol): s for s in services}
        dirty = []
        for asset_id, reported in self.services.items():
            asset = self.by_id[asset_id]
            for (port, protocol), seen in reported.items():
                service = existing.get((asset_id, port, protocol))
                details = {"service": seen.service, "product": seen.product}
                if service is None:
                    AssetService.objects.create(
                        asset=asset, port=port, protocol=protocol, service=seen.service, product=seen.product,
                        banner=seen.banner, first_seen_at=self.at, last_seen_at=self.at,
                    )
                    self._change(asset, Kind.SERVICE_OPENED, f"{port}/{protocol}", None, details)
                    continue
                before = (service.service, service.product, service.banner)
                reopened = service.closed_at is not None and self.at >= service.closed_at
                if reopened:
                    service.closed_at = None
                    self._change(asset, Kind.SERVICE_OPENED, f"{port}/{protocol}", None, details)
                if self.at >= service.last_seen_at:
                    service.service = seen.service or service.service
                    service.product = seen.product or service.product
                    service.banner = seen.banner or service.banner
                changed = (service.service, service.product, service.banner) != before
                if self._widen(service) or reopened or changed:
                    dirty.append(service)
        if closing:
            for (asset_id, port, protocol), service in existing.items():
                if (asset_id in self.probed and service.closed_at is None
                        and (port, protocol) not in self.services.get(asset_id, {})
                        and self.at >= service.last_seen_at):
                    service.closed_at = self.at
                    dirty.append(service)
                    self._change(self.by_id[asset_id], Kind.SERVICE_CLOSED, f"{port}/{protocol}", None, None)
        AssetService.objects.bulk_update(
            dirty, ["closed_at", "service", "product", "banner", "first_seen_at", "last_seen_at"]
        )

    # --- bookkeeping ----------------------------------------------------------

    def _change(self, asset: Asset, kind: str, field_name: str = "", old=None, new=None) -> None:
        self.changes.append(AssetChange(
            org=self.org, asset=asset, kind=kind, field=field_name, old_value=old, new_value=new,
            source_kind=self.batch.source_kind, job=self.job, occurred_at=clock.now(),
        ))
        if self.status.get(asset.id) == "unchanged":
            self.status[asset.id] = "updated"
        if kind != Kind.CREATED:
            self.dirty_assets.add(asset.id)

    def _widen(self, row) -> bool:
        """Stretch ``row``'s first/last seen window to this batch; True if it moved."""
        if row.first_seen_at <= self.at <= row.last_seen_at:
            return False
        row.first_seen_at = min(row.first_seen_at, self.at)
        row.last_seen_at = max(row.last_seen_at, self.at)
        return True

    def _flush(self) -> None:
        now = clock.now()
        assets = [self.by_id[asset_id] for asset_id in self.dirty_assets]
        for asset in assets:
            asset.updated_at = now
        fields = ["kind", "label", "attributes", "first_seen_at", "last_seen_at", "archived_at", "updated_at"]
        Asset.objects.bulk_update(assets, fields)
        AssetSource.objects.bulk_update(
            [self.sources[asset_id] for asset_id in self.dirty_sources],
            ["raw", "external_id", "first_seen_at", "last_seen_at"],
        )
        AssetChange.objects.bulk_create(self.changes)
