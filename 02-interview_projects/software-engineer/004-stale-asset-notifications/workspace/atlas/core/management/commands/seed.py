"""Deterministic demo data: ``python manage.py seed [--seed 42] [--scale N] [--reset]``.

Three orgs (docs/architecture.md §9) and eight weeks of simulated nightly imports ending at
2026-11-05T14:30Z: zone files, Nimbus exports and the CT feed every night at 03:15-04:05 org
time, port scans on Sundays. Rows are written with ``bulk_create`` in the shape that merge,
ownership and exposure produce, without running the importers or the merge; then the real
``apply_ownership`` and ``evaluate_assets`` run once per org at the anchor, so owners and
exposures are exactly what the code computes (they fix the few rows the shortcut gets wrong,
e.g. a certificate nobody has seen since its warning window began). Same arguments, same
rows and ids.

Volume: ~5,000 assets at ``--scale 1``. An org's volume is multiplied by
``1 + (scale - 1) * growth``; Quillstone's long tail of campaign microsites grows fastest,
so ``--scale 8`` gives Quillstone ~40k assets (docs/requests/REQ-0219).
"""

import ipaddress
import random
import time as stopwatch
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from fnmatch import fnmatchcase
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from atlas.assets.models import (
    Asset,
    AssetChange,
    AssetLink,
    AssetService,
    AssetSource,
    OwnershipRule,
    SavedView,
    Tag,
)
from atlas.assets.ownership import apply_ownership
from atlas.core import clock
from atlas.core.auth import issue_api_key
from atlas.core.models import ApiKey, Membership, Org
from atlas.exposure.models import Exposure
from atlas.exposure.service import evaluate_assets
from atlas.jobs.models import Job
from atlas.notify.models import EVENTS, Webhook

ANCHOR = datetime(2026, 11, 5, 14, 30, tzinfo=UTC)
FIRST_NIGHT = date(2026, 9, 11)  # local date of the first nightly import
NIGHTS = 56  # 2026-09-11 .. 2026-11-05
STALE_BEFORE = 42  # stale assets were last seen two weeks or more before the anchor
MIGRATED = 38  # 2026-10-19: Harborview's Nimbus account moved to the v2 id (docs/requests/CS-0412)
BATCH = 2000
SCHEDULE = {"zone_file": time(3, 15), "nimbus": time(3, 40), "ct_feed": time(4, 5),
            "port_scan": time(4, 30), "api": time(3, 0)}
SCAN_NIGHTS = [n for n in range(NIGHTS) if n == 0 or (FIRST_NIGHT + timedelta(n)).weekday() == 6]
SCANNER = "periscope external-weekly"
PATHS = {"nimbus": "nimbus/{}-{}.json", "ct_feed": "ct/{}-{}.jsonl", "port_scan": "scans/{}-{}.json",
         "zone_file": "zone/{2}.zone"}

SERVICES = ("api www app auth sso login portal mail vpn static img assets status docs admin grafana jenkins "
            "git search billing pay checkout media upload feeds dev sftp edge gw reports").split()
ENVS = ("", "", "", "-stg", "-dev", "-uat", "-dr")
CAMPAIGNS = ("spring summer autumn winter election budget worldcup festival awards holiday backtoschool "
             "blackfriday podcast newsletter quiz giveaway longread investigation sport culture").split()
ROLES = ("web", "api", "worker", "db", "cache", "batch", "ingest", "search", "backup", "q&a-widget")
RESOURCES = {"compute.instance": "i", "network.load_balancer": "lb", "storage.bucket": "bkt",
             "database.postgres": "db", "compute.function": "fn", "container.cluster": "k8s"}
ISSUERS = ("Fernway TLS Issuing CA R3", "Lumen Trust RSA CA 2025", "Brightwater DV CA E1")
PORTS = [entry for entry, weight in (  # (port, protocol, service, product, banner, admin UI), weight
    ((443, "tcp", "https", "nginx", "", False), 40), ((80, "tcp", "http", "nginx", "", False), 22),
    ((22, "tcp", "ssh", "OpenSSH 9.6", "SSH-2.0-OpenSSH_9.6", False), 10),
    ((8443, "tcp", "https", "Jenkins", "Jenkins admin console", True), 4),
    ((8080, "tcp", "http", "Apache Tomcat", "Tomcat Manager Application", True), 3),
    ((3000, "tcp", "http", "Grafana", "Grafana login", True), 2),
    ((25, "tcp", "smtp", "Postfix", "220 mail ESMTP Postfix", False), 3),
    ((3389, "tcp", "rdp", "", "", False), 1), ((5432, "tcp", "postgresql", "PostgreSQL 15", "", False), 1),
    ((9200, "tcp", "http", "Elasticsearch", "", False), 1), ((500, "udp", "isakmp", "", "", False), 1),
) for _ in range(weight)]


@dataclass
class Profile:
    """One demo org. Space-separated strings keep the table short; ``__post_init__`` splits them."""

    name: str
    timezone: str
    allowed_ports: list
    api_key: str
    webhook_secret: str
    base: int  # assets at --scale 1
    growth: float
    domains: str  # names under .example.test; the first one is Org.domain
    zones: str  # sub-zones of Org.domain; repeats weigh the choice
    tags: str
    nimbus: str  # account id [v2 account id after the MIGRATED night]
    regions: str
    networks: str  # public IPv4, public IPv6, internal
    rules: tuple  # "pattern_type pattern team priority [disabled]"; {} is Org.domain

    def __post_init__(self):
        self.domains = tuple(f"{d}.example.test" for d in self.domains.split())
        for name in ("zones", "tags", "nimbus", "regions", "networks"):
            setattr(self, name, tuple(getattr(self, name).split()))
        self.rules = tuple(rule.format(self.domains[0]) for rule in self.rules)


PROFILES = {
    "harborview-bank": Profile(
        "Harborview Bank", "America/Toronto", [443], "atl_DEMO_k5lv9z8g76x8az3c8x0ajrk98pwkji8f",
        "DEMO-whsec-harborview-bank-e33d70005377", 1300, 1.0,
        "harborview-bank hvbank harborview-online harborview-mortgage",
        "payments online online api corp branch cards mortgage",
        "pci prod staging internet-banking legacy third-party", "4471-2210-0093 acct-7f3k9q2mwd",
        "ca-central-2 ca-east-1", "198.51.100.0/24 2001:db8:4b0::/48 10.20.0.0/16",
        ("hostname *.payments.{} payments-platform 10", "hostname *.cards.{} payments-platform 10",
         "hostname *.online.{} digital-banking 20", "hostname *.corp.{} corp-it 30",
         "cidr 10.20.0.0/16 corp-it 40", "tag third-party vendor-management 50",
         "hostname *.mortgage.{} mortgage-apps 60 disabled", "cidr 198.51.100.0/24 network-engineering 90",
         "hostname *.{} platform-sre 100")),
    "quillstone-media": Profile(
        "Quillstone Media", "Europe/London", [80, 443], "atl_DEMO_lk3derxtk5a6cyct4gpy0cv4d8mbeooy",
        "DEMO-whsec-quillstone-media-a193907f8b4b", 2900, 1.83,
        "quillstone-media quillstone-news qsm-cdn morningledger quillstone-podcasts",
        "cms cdn video newsroom ads podcasts" + " campaigns" * 5,
        "prod staging campaign cdn legacy video", "8812-0457-3301", "eu-west-2 eu-north-1",
        "203.0.113.0/24 2001:db8:9e1::/48 10.30.0.0/16",
        ("hostname *.campaigns.{} growth-marketing 10", "hostname *.video.{} video-platform 20",
         "hostname *.cdn.{} edge 20", "tag legacy web-platform 30", "hostname *.{} web-platform 100",
         "hostname *.morningledger.example.test morning-ledger 100")),
    "orchid-grid": Profile(
        "Orchid Grid", "Pacific/Auckland", [22, 443, 8443], "atl_DEMO_k8p4pxiky19mehziqutg5ri41pvcx876",
        "DEMO-whsec-orchid-grid-3897bfee30d5", 800, 1.0, "orchid-grid orchid-energy og-field",
        "portal portal meter ops vpn grid-api scada-gw", "ot prod scada vendor legacy field",
        "acct-2m8x4c1pzq", "ap-southeast-4 ap-southeast-2", "203.0.113.0/24 2001:db8:6f1::/48 10.40.0.0/16",
        ("hostname *.scada-gw.{} ot-security 10", "tag ot ot-security 20", "cidr 10.40.0.0/16 ot-security 30",
         "hostname *.portal.{} customer-portal 40", "hostname *.{} infrastructure 100",
         "cidr 203.0.113.0/24 infrastructure 100")),
}
SAVED_VIEWS = {"Changed in last 24h": "changed_within=24", "Unowned hosts": "kind=host&owner=-",
               "Expiring certificates": "exposure=cert_expiring&kind=certificate",
               "Public IPs with exposures": "exposure=any&kind=ip"}
EXTRA_VIEWS = {"harborview-bank": ("PCI scope", "tag=pci"),
               "orchid-grid": ("OT exposure", "exposure=any&tag=ot"),
               "quillstone-media": ("Campaign microsites", "kind=host&q=campaigns")}


def inside(key: str, cidr: str) -> bool:
    """An IP or network ``key`` within ``cidr`` (same version), as cidr ownership rules match."""
    item, network = ipaddress.ip_network(key), ipaddress.ip_network(cidr)
    return item.version == network.version and item.subnet_of(network)


def asset_target(slug: str, scale: int) -> int:
    profile = PROFILES[slug]
    return round(profile.base * (1 + (scale - 1) * profile.growth))


@dataclass
class Spec:
    """One asset while it is being invented; days are night indexes (0 .. NIGHTS - 1)."""

    asset: Asset
    first: int
    last: int
    sources: dict = field(default_factory=dict)  # source name -> [first night, last night]; primary first
    links: list = field(default_factory=list)  # (relation, target Spec)
    services: list = field(default_factory=list)  # (PORTS entry, first scan night, closed night | None)
    tags: dict = field(default_factory=dict)  # tag name -> night
    public: bool = False
    renamed: tuple | None = None  # (old label, night)

    def see(self, source: str, night: int) -> None:
        self.sources.setdefault(source, [max(night, self.first), self.last])


class OrgSeeder:
    def __init__(self, slug: str, seed: int, scale: int):
        self.slug, self.p = slug, PROFILES[slug]
        self.rng = random.Random(f"{seed}:{slug}")
        self.target = asset_target(slug, scale)
        self.tz = ZoneInfo(self.p.timezone)
        self.specs: list[Spec] = []
        self.keys: set[tuple[str, str]] = set()
        # source name -> (source kind, minutes after the scheduled time, nights it ran)
        self.kinds = {f"{d} zone": ("zone_file", i * 2, range(NIGHTS)) for i, d in enumerate(self.p.domains)}
        old, new = (*self.p.nimbus, "")[:2]
        self.kinds[f"nimbus account {old}"] = ("nimbus", 0, range(MIGRATED if new else NIGHTS))
        if new:
            self.kinds[f"nimbus account {new}"] = ("nimbus", 0, range(MIGRATED, NIGHTS))
        self.kinds |= {"ct feed": ("ct_feed", 0, range(NIGHTS)), SCANNER: ("port_scan", 0, SCAN_NIGHTS),
                       "api": ("api", 0, ())}

    # -- time ---------------------------------------------------------------------------------
    def night(self, source: str, day: int) -> int:
        return max(n for n in SCAN_NIGHTS if n <= day) if self.kinds[source][0] == "port_scan" else day

    def when(self, source: str, day: int) -> datetime:
        kind, offset, _ = self.kinds[source]
        local = datetime.combine(FIRST_NIGHT + timedelta(self.night(source, day)), SCHEDULE[kind], self.tz)
        return (local + timedelta(minutes=offset)).astimezone(UTC)

    def stamp(self, source: str, day: int) -> tuple[datetime, Job | None]:
        """When the import of ``source`` on night ``day`` wrote a row, and that job."""
        at = self.when(source, day) + timedelta(seconds=self.rng.randint(2, 50))
        return at, self.jobs.get((source, self.night(source, day)))

    def daytime(self, day: int) -> datetime:
        """Office hours on that local day: someone using the API or the dashboard."""
        local = datetime.combine(FIRST_NIGHT + timedelta(day), time(self.rng.randint(8, 18)), self.tz)
        at = (local + timedelta(minutes=self.rng.randint(0, 59))).astimezone(UTC)
        return at - timedelta(days=1) if at > ANCHOR else at

    def day_of(self, at: datetime) -> int:
        return min(max((at.astimezone(self.tz).date() - FIRST_NIGHT).days, 0), NIGHTS - 1)

    # -- inventory ----------------------------------------------------------------------------
    def add(self, kind, key, label, attributes, source, first=None, steady=False) -> Spec:
        rng = self.rng
        if first is None:
            first = 0 if rng.random() < 0.62 else rng.randrange(1, NIGHTS)
        last = NIGHTS - 1
        if not steady and first < STALE_BEFORE and rng.random() < 0.08:
            last = rng.randrange(first, STALE_BEFORE)
        spec = Spec(Asset(org=self.org, kind=kind, key=key, label=label, attributes=attributes), first, last)
        spec.sources[source] = [first, last]
        self.keys.add((kind, key))
        self.specs.append(spec)
        return spec

    def host_key(self, zone: str) -> str:
        rng = self.rng
        while True:
            if zone.startswith("campaigns."):
                name = f"{rng.choice(CAMPAIGNS)}-{rng.randint(2018, 2026)}-{rng.randint(1, 999):03d}"
            else:
                number = f"-{rng.randint(1, 60):02d}" if rng.random() < 0.6 else ""
                name = rng.choice(SERVICES) + rng.choice(ENVS) + number
            if ("host", f"{name}.{zone}") not in self.keys:
                return f"{name}.{zone}"

    def generate(self) -> None:
        p, rng, apex = self.p, self.rng, self.p.domains[0]
        free = self.target - len(p.domains) - len(p.networks)
        n_ip, n_cert, n_cloud = round(free * 0.20), round(free * 0.12), round(free * 0.14)
        for d in p.domains:
            self.add("domain", d, d, {"zone": d}, f"{d} zone", first=0, steady=True)
        networks = [ipaddress.ip_network(c) for c in p.networks]
        nets = [self.add("network", str(n), str(n), {"version": n.version}, "api", 0, True) for n in networks]
        pool = list(networks[0].hosts())
        rng.shuffle(pool)
        ips = []
        while len(ips) < n_ip:
            net = 0 if pool else (1 if rng.random() < 0.55 else 2)
            size = min(networks[net].num_addresses - 1, 2**32)
            addr = pool.pop() if pool else networks[net][rng.randrange(1, size)]
            if ("ip", str(addr)) in self.keys:
                continue
            source = SCANNER if net < 2 else f"{apex} zone"
            ip = self.add("ip", str(addr), str(addr), {"version": addr.version}, source)
            ip.public = net < 2
            nets[net].links.append(("contains", ip))
            ports = {rng.choice(PORTS) for _ in range(rng.choice((1, 1, 2, 2, 3)))} if ip.public else ()
            for entry in sorted(ports):
                first = self.night(SCANNER, ip.first)
                later = [n for n in SCAN_NIGHTS if first < n <= ip.last]
                closed = rng.choice(later) if later and rng.random() < 0.12 else None
                ip.services.append((entry, first, closed))
            ips.append(ip)
        by_zone, resolving = defaultdict(list), []
        for _ in range(free - n_ip - n_cert - n_cloud):
            zone = f"{rng.choice(p.zones)}.{apex}" if rng.random() < 0.85 else rng.choice(p.domains[1:])
            domain = zone if zone in p.domains else apex
            in_zone, roll = rng.random() < 0.75, rng.random()
            attrs, source = ({"zone": domain}, f"{domain} zone") if in_zone else ({}, "ct feed")
            key = self.host_key(zone)
            host = self.add("host", key, key, attrs, source)
            by_zone[zone].append(host)
            if not in_zone:
                continue
            if roll < 0.015:  # CNAME to a deleted Nimbus static site
                site = f"{self.slug.split('-')[0]}-{rng.choice(SERVICES)}-{rng.randint(1, 999)}"
                target = f"{site}.pages.nimbus-apps.example.test"
                if ("host", target) not in self.keys:
                    host.links.append(("cname", self.add("host", target, target, {}, source, host.first)))
            elif roll < 0.09 and resolving:
                host.links.append(("cname", rng.choice(resolving)))
            elif roll < 0.93:
                ip = rng.choice(ips)
                ip.see(source, host.first)
                host.links.append(("resolves_to", ip))
                resolving.append(host)
        zones = sorted(by_zone)
        for _ in range(n_cert):
            zone = rng.choice(zones)
            siblings = by_zone[zone]
            if len(siblings) <= 300 and rng.random() < 0.15:
                cn, covered = f"*.{zone}", siblings
            else:
                covered = rng.sample(siblings, min(len(siblings), rng.randint(1, 4)))
                cn = covered[0].asset.key
            validity = rng.choice((90, 90, 397))  # 90-day certificates renew at 60 days; a few lapse
            lapsed = rng.random() < 0.04
            span = 60 if validity == 90 else validity
            age = validity + rng.randint(0, 20) if lapsed else rng.randint(0, span)
            not_before = ANCHOR - timedelta(days=age, hours=rng.randint(0, 23))
            not_after = not_before + timedelta(days=validity)
            attrs = {"subject_cn": cn, "sans": [cn] + [h.asset.key for h in covered if h.asset.key != cn],
                     "issuer": rng.choice(ISSUERS), "serial": f"{rng.getrandbits(64):016x}",
                     "not_before": clock.isoformat(not_before), "not_after": clock.isoformat(not_after)}
            first = max(self.day_of(not_before), 0 if rng.random() < 0.62 else rng.randrange(NIGHTS))
            cert = self.add("certificate", f"{rng.getrandbits(256):064x}", cn, attrs, "ct feed", first)
            for host in covered:
                host.see("ct feed", cert.first)
                cert.links.append(("covers", host))
        initials = "".join(word[0] for word in self.slug.split("-"))
        old, new = (*p.nimbus, "")[:2]
        for _ in range(n_cloud):
            rtype = rng.choice(list(RESOURCES))
            rid = f"{RESOURCES[rtype]}-{rng.getrandbits(40):010x}"
            env = rng.choice(("prod", "prod", "stg", "dev"))
            name = f"{initials}-{rng.choice(ROLES)}-{env}-{rng.randint(1, 40):02d}"
            exposed = rtype in ("compute.instance", "network.load_balancer") and rng.random() < 0.6
            ip = rng.choice(ips[:254]) if exposed else None
            attrs = {"provider": "nimbus", "resource_type": rtype, "region": rng.choice(p.regions),
                     "public_ip": ip.asset.key if ip else None}
            first = 0 if rng.random() < 0.62 else rng.randrange(1, NIGHTS)
            account = new if new and first >= MIGRATED else old
            while account:
                source = f"nimbus account {account}"
                cloud = self.add("cloud_resource", f"nimbus:{account}:{rid}", name,
                                 attrs | {"account_id": account}, source, first)
                twin = account == old and new and cloud.last >= MIGRATED
                if twin:  # Nimbus v2 exports carry the new account id: same resource, second key
                    cloud.last = cloud.sources[source][1] = MIGRATED - 1
                if cloud.last > cloud.first and rng.random() < 0.25:
                    cloud.renamed = (rid, rng.randint(cloud.first + 1, cloud.last))
                if ip:
                    ip.see(source, cloud.first)
                    cloud.links.append(("attached", ip))
                account, first = (new, MIGRATED) if twin else ("", 0)
        for spec in self.specs:
            if rng.random() < 0.35:
                spec.tags[rng.choice(p.tags)] = rng.randint(spec.first, spec.last)
            if "staging" in p.tags and any(m in spec.asset.label for m in ("-stg", "-uat", "-dev")):
                spec.tags.setdefault("staging", spec.first)

    def owner(self, spec: Spec) -> OwnershipRule | None:
        """Same precedence as atlas.assets.ownership: enabled rules by (priority, id), first match."""
        a = spec.asset
        for rule in self.rules:
            kind = rule.pattern_type
            if rule.enabled and (
                (kind == "hostname" and a.kind in ("host", "domain") and fnmatchcase(a.key, rule.pattern))
                or (kind == "cidr" and a.kind in ("ip", "network") and inside(a.key, rule.pattern))
                or (kind == "tag" and rule.pattern in spec.tags)
            ):
                return rule
        return None

    # -- rows ---------------------------------------------------------------------------------
    def seed(self) -> Counter:
        p = self.p
        onboarded = datetime.combine(FIRST_NIGHT - timedelta(days=1), time(10), self.tz).astimezone(UTC)
        self.org = Org.objects.create(slug=self.slug, name=p.name, domain=p.domains[0], timezone=p.timezone,
                                      allowed_ports=p.allowed_ports, created_at=onboarded)
        key, _ = issue_api_key(self.org, "demo", raw=p.api_key)
        ApiKey.objects.filter(pk=key.pk).update(created_at=onboarded)
        Webhook.objects.create(org=self.org, name="mockhook", url=f"http://mockhook:9000/hooks/{self.slug}",
                               secret=p.webhook_secret, events=list(EVENTS), created_at=onboarded)
        self.tags = {name: Tag(org=self.org, name=name, created_at=onboarded) for name in p.tags}
        Tag.objects.bulk_create(self.tags.values())
        rules = [r.split() for r in p.rules]
        self.rules = OwnershipRule.objects.bulk_create(
            OwnershipRule(org=self.org, pattern_type=r[0], pattern=r[1], team=r[2], priority=int(r[3]),
                          enabled=len(r) == 4, created_at=onboarded) for r in rules)
        self.rules.sort(key=lambda rule: (rule.priority, rule.id))
        views = SAVED_VIEWS | dict([EXTRA_VIEWS[self.slug]])
        SavedView.objects.bulk_create(SavedView(org=self.org, name=name, querystring=qs, created_at=onboarded)
                                      for name, qs in views.items())
        self.jobs = {}
        for source, (kind, _, nights) in self.kinds.items():
            for night in nights:
                at = self.when(source, night)
                day = FIRST_NIGHT + timedelta(night)
                path = PATHS[kind].format(self.slug, day, source.removesuffix(" zone"))
                self.jobs[source, night] = Job(
                    org=self.org, kind="import.run", status=Job.Status.DONE, attempts=1, run_after=at,
                    payload={"importer": kind, "path": path, "source_name": source}, created_at=at,
                    locked_by="worker-1", locked_at=at,
                    finished_at=at + timedelta(seconds=self.rng.randint(9, 90)))
        self.generate()
        rows, changes = self.build()
        self.job_results(changes)
        Job.objects.bulk_create(self.jobs.values(), batch_size=BATCH)
        Asset.objects.bulk_create([s.asset for s in self.specs], batch_size=BATCH)
        for model in (AssetSource, AssetLink, AssetService, Asset.tags.through, Exposure):
            model.objects.bulk_create(rows[model], batch_size=BATCH)
        for change in changes:
            if isinstance(e := change.new_value, Exposure):
                change.new_value = {"exposure_id": e.pk, "subject": e.subject, "severity": e.severity}
        changes.sort(key=lambda c: c.occurred_at)  # stable: ids follow time, ties keep build order
        AssetChange.objects.bulk_create(changes, batch_size=BATCH)
        # The real rules have the last word (at the anchor: the clock is frozen there).
        fixes = len(apply_ownership(self.org))
        evaluation = evaluate_assets(self.org)
        fixes += len(evaluation.opened) + len(evaluation.resolved)
        open_exposures = Exposure.objects.for_org(self.org).filter(status="open").count()
        return Counter(assets=len(self.specs), sources=len(rows[AssetSource]), links=len(rows[AssetLink]),
                       services=len(rows[AssetService]), changes=len(changes) + fixes, jobs=len(self.jobs),
                       open_exposures=open_exposures, rule_fixes=fixes)

    def build(self) -> tuple[dict, list[AssetChange]]:
        rng, rows, changes = self.rng, defaultdict(list), []
        teams = sorted({rule.team for rule in self.rules})

        def change(spec, kind, at, source, job=None, field="", old=None, new=None):
            changes.append(AssetChange(
                org=self.org, asset=spec.asset, kind=kind, occurred_at=at, job=job, field=field,
                source_kind=self.kinds[source][0], old_value=old, new_value=new))

        def expose(spec, rule, subject, severity, title, details, opened, job, resolved=None, rjob=None):
            resolved = resolved or spec.asset.archived_at
            e = Exposure(org=self.org, asset=spec.asset, rule=rule, subject=subject, severity=severity,
                         status="resolved" if resolved else "open", title=title[:300], details=details,
                         opened_at=opened, resolved_at=resolved,
                         last_evaluated_at=resolved or spec.asset.last_seen_at)
            rows[Exposure].append(e)
            change(spec, "exposure_opened", opened, primary, job, field=rule, new=e)
            if resolved:
                change(spec, "exposure_resolved", resolved, SCANNER if rjob else "api", rjob, rule, new=e)

        for spec in self.specs:
            a, start, primary = spec.asset, len(changes), next(iter(spec.sources))
            a.first_seen_at = a.created_at = self.when(primary, spec.first)
            a.last_seen_at = max(self.when(name, last) for name, (_, last) in spec.sources.items())
            if spec.last < 30 and a.kind not in ("domain", "network") and rng.random() < 0.3:
                a.archived_at = self.daytime(spec.last + 14)
            at, job = self.stamp(primary, spec.first)
            change(spec, "created", at, primary, job)
            for name, (first, last) in spec.sources.items():
                kind = self.kinds[name][0]
                rows[AssetSource].append(AssetSource(
                    asset=a, source_kind=kind, source_name=name, raw=a.attributes if name == primary else {},
                    external_id=a.key.split(":")[2] if a.kind == "cloud_resource" else "",
                    first_seen_at=self.when(name, first), last_seen_at=self.when(name, last)))
                if name != primary:
                    at, job = self.stamp(name, first)
                    change(spec, "source_added", at, name, job, field=kind, new=name)
            if spec.renamed:
                at, job = self.stamp(primary, spec.renamed[1])
                change(spec, "updated", at, primary, job, field="label", old=spec.renamed[0], new=a.label)
            for relation, target in spec.links:
                first = max(spec.first, target.first)
                at, job = self.stamp(primary, first)
                last = max(at, self.when(primary, max(first, min(spec.last, target.last))))
                rows[AssetLink].append(AssetLink(asset=a, target=target.asset, relation=relation,
                                                 first_seen_at=at, last_seen_at=last,
                                                 source_kind=self.kinds[primary][0]))
                change(spec, "link_added", at, primary, job, field=relation, new=target.asset.key)
                if relation == "cname" and not target.links:
                    expose(spec, "dangling_cname", target.asset.key, "high",
                           f"{a.key} is a CNAME to {target.asset.key}, which does not resolve",
                           {"target": target.asset.key}, at, job)
            for (port, proto, service, product, banner, admin), first, closed in spec.services:
                opened, job = self.stamp(SCANNER, first)
                closed_at, cjob = self.stamp(SCANNER, closed) if closed is not None else (None, None)
                last = max(n for n in SCAN_NIGHTS if n < closed) if closed is not None else spec.last
                rows[AssetService].append(AssetService(
                    asset=a, port=port, protocol=proto, service=service, product=product, banner=banner,
                    first_seen_at=self.when(SCANNER, first), last_seen_at=self.when(SCANNER, last),
                    closed_at=closed_at))
                subject = f"{port}/{proto}"
                change(spec, "service_opened", opened, SCANNER, job, field=subject,
                       new={"service": service, "product": product})
                if closed_at:
                    change(spec, "service_closed", closed_at, SCANNER, cjob, field=subject)
                if port not in self.p.allowed_ports:
                    expose(spec, "unexpected_port", subject, "medium",
                           f"Unexpected open port {subject} on {a.key}",
                           {"port": port, "protocol": proto, "service": service},
                           opened, job, closed_at, cjob)
                if admin:
                    expose(spec, "admin_panel_public", subject, "high", f"{product} admin UI on {a.key}",
                           {"port": port, "product": product, "banner": banner}, opened, job, closed_at, cjob)
            if a.kind == "certificate":
                not_after = datetime.fromisoformat(a.attributes["not_after"])
                days = (not_after.astimezone(self.tz).date() - ANCHOR.astimezone(self.tz).date()).days
                first = max(spec.first, self.day_of(not_after - timedelta(days=self.org.cert_warning_days)))
                if days <= self.org.cert_warning_days and first <= spec.last:
                    verb = "expired" if days < 0 else "expires"
                    expose(spec, "cert_expiring", "", "critical" if days < 0 else "medium",
                           f"Certificate for {a.label} {verb} on {not_after.date()}",
                           {"not_after": a.attributes["not_after"], "days_left": days},
                           *self.stamp(primary, first))
            for name, day in spec.tags.items():
                rows[Asset.tags.through].append(Asset.tags.through(asset=a, tag=self.tags[name]))
                change(spec, "tagged", self.daytime(day), "api", field="tag", new=name)
            if rule := self.owner(spec):
                a.owner_team = rule.team
                by_tag = rule.pattern_type == "tag"
                at, job = (self.daytime(spec.tags[rule.pattern]), None) if by_tag else (
                    self.stamp(primary, spec.first))
                change(spec, "owner_changed", at, "api" if by_tag else primary, job, field="owner_team",
                       old="", new=rule.team)
            if a.kind == "host" and rng.random() < 0.01:  # set by hand in the dashboard: locked
                team = rng.choice(teams)
                at = self.daytime(rng.randint(spec.first, spec.last))
                change(spec, "owner_changed", at, "api", field="owner_team", old=a.owner_team, new=team)
                a.owner_team, a.owner_locked = team, True
            if a.archived_at:
                change(spec, "archived", a.archived_at, "api")
            a.updated_at = max(c.occurred_at for c in changes[start:])
        return rows, changes

    def job_results(self, changes: list[AssetChange]) -> None:
        counts = defaultdict(Counter)
        for c in changes:
            if c.job is not None:
                counts[id(c.job)][c.kind] += 1
        alive = defaultdict(Counter)  # source name -> night -> +1 when an asset starts, -1 after it stops
        for spec in self.specs:
            for name, (first, last) in spec.sources.items():
                alive[name][first] += 1
                alive[name][last + 1] -= 1
        for (source, night), job in self.jobs.items():
            n = counts[id(job)]
            seen = max(sum(v for d, v in alive[source].items() if d <= night), n["created"])
            job.result = {"importer": job.payload["importer"], "source_name": source, "observations": seen,
                          "created": n["created"], "updated": n["updated"], "warnings": [],
                          "unchanged": max(seen - n["created"] - n["updated"], 0), "events": 0,
                          "exposures_opened": n["exposure_opened"],
                          "exposures_resolved": n["exposure_resolved"]}


class Command(BaseCommand):
    help = "Load deterministic demo data: 3 orgs, ~5,000 assets x scale, 8 weeks of history."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--scale", type=int, default=1, help="volume multiplier (8: Quillstone ~40k)")
        parser.add_argument("--reset", action="store_true", help="delete every org and its data first")

    def handle(self, *args, seed: int, scale: int, reset: bool, **options):
        if scale < 1:
            raise CommandError("--scale must be 1 or more")
        started = stopwatch.monotonic()
        with transaction.atomic(), clock.frozen(ANCHOR):
            if Org.objects.exists() and not reset:
                raise CommandError("Orgs already exist. Run `make seed SEED_ARGS=--reset` (deletes all "
                                   "customer data) or `make clean` first.")
            members = list(Membership.objects.values_list("user_id", "org__slug", "role"))
            with connection.cursor() as cursor:  # restarts the id sequences too: same seed, same ids
                cursor.execute(f"SET CONSTRAINTS ALL IMMEDIATE; TRUNCATE {Org._meta.db_table} "
                               "RESTART IDENTITY CASCADE; SET CONSTRAINTS ALL DEFERRED")
            orgs = {}
            for slug in PROFILES:
                seeder = OrgSeeder(slug, seed, scale)
                counts = seeder.seed()
                orgs[slug] = seeder.org
                self.stdout.write(f"{slug}: " + ", ".join(f"{v:,} {k}" for k, v in counts.items()))
            Membership.objects.bulk_create(Membership(user_id=user, org=orgs[slug], role=role)
                                           for user, slug, role in members if slug in orgs)
        elapsed = stopwatch.monotonic() - started
        self.stdout.write(self.style.SUCCESS(f"Seeded --seed {seed} --scale {scale} in {elapsed:.1f}s"))
