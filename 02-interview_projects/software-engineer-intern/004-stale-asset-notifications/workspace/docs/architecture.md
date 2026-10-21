# Architecture

Owner: Olivia Chen. Last reviewed for 0.14 (2026-10). Decisions with history
are in `docs/adr/`. The models in `atlas/*/models.py` are the source of truth
for fields; this page says how the parts fit and what each one promises the
others.

Atlas keeps an inventory of each customer's internet-facing assets. Sources
(DNS zone files, Nimbus cloud exports, a certificate-transparency feed, port
scans) are imported as jobs; the merge step folds them into one asset per
identity with provenance; ownership rules assign a team; exposure rules flag
risky assets; every change lands in an append-only history and goes out as
signed webhooks. A REST API and a server-rendered dashboard sit on top. One
Django project, one Postgres database, three processes (`web`, `worker`,
and the dev-only `mockhook`). See ADR 0001.

## 1. Components

| Component | Paths | Owner | Runs in |
|---|---|---|---|
| core | `atlas/core/` (not `seed.py`/`create_demo_user.py`), `atlas/settings/`, `atlas/urls.py`, every `models.py` and `migrations/`, `tests/conftest.py`, `tests/factories.py`, Docker/Makefile | Olivia Chen | all |
| api | `atlas/api/`, `atlas/assets/filters.py`, `atlas/assets/ownership.py` | Daniel Mensah | web |
| importers | `atlas/importers/`, `fixtures/imports/` | Aiko Tanaka (`ct_feed.py` by Zoe Park) | worker |
| merge | `atlas/merge/` | Aiko Tanaka | worker |
| jobs | `atlas/jobs/` (not `models.py`) | Aiko Tanaka | worker |
| exposure | `atlas/exposure/` (not `models.py`) | Aiko Tanaka | worker |
| notify | `atlas/notify/` (not `models.py`), `mockhook/` | Daniel Mensah | worker, mockhook |
| dashboard | `atlas/dashboard/` | Rafael Souza | web |
| seed, bench | `atlas/core/management/commands/seed.py`, `create_demo_user.py`, `scripts/bench.py` | Olivia Chen | one-off |

Apps (`INSTALLED_APPS` labels): `core`, `jobs`, `assets`, `exposure`,
`notify`, `dashboard`. `atlas/importers/`, `atlas/merge/` and `atlas/api/`
are plain packages.

## 2. One import, end to end

1. `python manage.py enqueue_import --org harborview-bank --importer zone_file
   --path zone/harborview-bank.example.test.zone` calls
   `atlas.jobs.queue.enqueue(...)`: a `jobs` row, `queued`.
2. `run_worker` claims it (`FOR UPDATE SKIP LOCKED`, own transaction,
   `attempts + 1`).
3. The worker (`jobs.worker.execute`) opens **one** `transaction.atomic()`
   around the `import.run` handler and `queue.complete()`; the handler:
   1. reads the file (path must stay inside `ATLAS_IMPORT_ROOT`),
   2. `importers.registry.get_importer(name)(text)` -> `ImportBatch`,
   3. `merge.service.merge_batch(org, batch, job=job)` -> `MergeResult`,
   4. `assets.ownership.apply_ownership(org, result.touched, job=job)`,
   5. `exposure.service.evaluate_assets(org, result.touched, job=job)`,
   6. `notify.outbox.publish_changes(org, all changes from 3-5)` and
      `notify.outbox.enqueue(org, "import.completed", {...})`.
4. On an exception everything above rolls back and `queue.fail()` records
   the error in a new transaction (retry with backoff, or `dead`).
5. Each worker iteration also calls `notify.delivery.deliver_due()`, which
   POSTs due outbox rows to webhook URLs with an HMAC signature.

## 3. Data model

All customer data carries `org` (directly, or through `asset` for
`AssetSource`, `AssetLink`, `AssetService`). Timestamps are aware UTC and
default to `atlas.core.clock.now`.

| Model (table) | Key fields | Notes |
|---|---|---|
| `core.Org` | `slug` (unique), `name`, `domain`, `timezone` (IANA), `allowed_ports` (JSON list of ints), `cert_warning_days` (30) | demo orgs in §9 |
| `core.ApiKey` | `org`, `name`, `prefix` (first 16 chars, indexed), `key_hash` (sha256 hex, unique), `last_used_at`, `revoked_at` | raw key never stored |
| `core.Membership` | `user`, `org`, `role` (`viewer`/`editor`); unique (user, org) | dashboard access |
| `assets.Asset` | `org`, `kind`, `key`, `label`, `attributes` (JSON), `owner_team`, `owner_locked`, `tags` (M2M `Tag`), `first_seen_at`, `last_seen_at`, `created_at`, `updated_at`, `archived_at`; unique (org, kind, key); index (org, last_seen_at) | kinds: `domain`, `host`, `ip`, `network`, `certificate`, `cloud_resource` |
| `assets.AssetSource` | `asset`, `source_kind`, `source_name`, `external_id`, `raw` (JSON), `first_seen_at`, `last_seen_at`; unique (asset, source_kind, source_name) | provenance; kinds `zone_file`, `nimbus`, `ct_feed`, `port_scan`, `api` |
| `assets.AssetLink` | `asset` -> `target`, `relation`, `source_kind`, `first_seen_at`, `last_seen_at`; unique (asset, target, relation) | `resolves_to` host->ip, `cname` host->host, `covers` certificate->host, `contains` network->ip, `attached` cloud_resource->ip/host |
| `assets.AssetService` | `asset`, `port`, `protocol` (`tcp`/`udp`), `service`, `product`, `banner`, `first_seen_at`, `last_seen_at`, `closed_at`; unique (asset, port, protocol) | open ports; `closed_at` set when a later scan of the asset no longer sees it |
| `assets.Tag` | `org`, `name` (slug), `description`; unique (org, name) | |
| `assets.OwnershipRule` | `org`, `pattern_type` (`hostname`/`cidr`/`tag`), `pattern`, `team`, `priority` (lower wins), `enabled` | ordered (priority, id) |
| `assets.AssetChange` | `org`, `asset`, `kind`, `field`, `old_value`/`new_value` (JSON), `source_kind`, `job` (nullable FK), `occurred_at`; indexes (org, occurred_at), (asset, occurred_at) | append-only; kinds below |
| `assets.SavedView` | `org`, `owner` (user, null = shared), `name`, `querystring`; unique (org, owner, name) with NULLs equal | |
| `exposure.Exposure` | `org`, `asset`, `rule`, `subject`, `severity`, `status` (`open`/`resolved`), `title`, `details` (JSON), `opened_at`, `last_evaluated_at`, `resolved_at`; unique (asset, rule, subject) where status = open | rules in §4.6 |
| `notify.Webhook` | `org`, `name`, `url`, `secret`, `events` (JSON list), `enabled` | events in §5 |
| `notify.OutboxEvent` | `org`, `webhook`, `event`, `payload` (the envelope's `data`), `status` (`pending`/`delivered`/`failed`/`dead`), `attempts`, `next_attempt_at`, `last_status_code`, `last_error`, `delivered_at`; index (status, next_attempt_at) | |
| `jobs.Job` | `org`, `kind`, `payload`, `status` (`queued`/`running`/`done`/`failed`/`dead`), `attempts`, `max_attempts` (5), `run_after`, `locked_by`, `locked_at`, `last_error`, `result`, `finished_at`; index (status, run_after) | |

**Asset keys** (built by `atlas.merge.identity.identity_key`):
`domain`/`host` normalized hostname (`normalize_hostname`), `ip`
`normalize_ip`, `network` `normalize_cidr`, `certificate` lower-case SHA-256
hex of the DER, `cloud_resource` `nimbus:<account_id>:<resource_id>` lower-case.
`label` is free text from the most recent source (hostname, certificate
subject CN, Nimbus resource name) and must be escaped wherever it is shown.

**Attributes** by kind: `ip`/`network` `{"version": 4|6}`; `certificate`
`{"subject_cn", "sans": [...], "issuer", "serial", "not_before", "not_after"}`
(ISO 8601 UTC strings); `cloud_resource` `{"provider": "nimbus",
"account_id", "resource_type", "region", "public_ip"}`; `host`/`domain`
`{"zone": "<origin>"}` when known.

**AssetChange kinds**: `created`, `updated` (one row per changed field:
`label`, `attributes`, `archived_at` on a restore, `kind` when a host becomes
the zone's domain), `source_added`, `link_added`, `service_opened`,
`service_closed`, `owner_changed`, `tagged`, `untagged`, `exposure_opened`,
`exposure_resolved`, `archived`. `field`/`old_value`/`new_value` carry the
detail (`link_added`: `field` = relation, `new_value` = target key;
`service_*`: `field` = `"443/tcp"`; `exposure_*`: `field` = rule,
`new_value` = `{"exposure_id", "subject", "severity"}`).

## 4. Contracts

Signatures below are the interface between components. Anything not listed is
private to its component.

### 4.1 core (`atlas/core/`)

```python
# atlas/core/clock.py
def now() -> datetime                                  # aware UTC; the only clock to use
def local_date(tz: str, at: datetime | None = None) -> date
def isoformat(value: datetime) -> str                  # "2026-11-05T14:30:00Z"
def freeze(at: datetime) -> None; def advance(**timedelta_kwargs) -> datetime
def unfreeze() -> None; def frozen(at: datetime) -> ContextManager[None]

# atlas/core/normalize.py      (raise NormalizationError(ValueError))
def normalize_hostname(value: str, *, allow_wildcard: bool = False) -> str
def normalize_ip(value: str) -> str
def normalize_cidr(value: str) -> str
def ip_in_network(ip: str, cidr: str) -> bool
def is_public_ip(ip: str) -> bool        # documentation ranges count as public

# atlas/core/auth.py
class ApiKeyAuthentication(BaseAuthentication)  # "Authorization: Bearer atl_DEMO_..."
class ApiClient: org: Org; api_key: ApiKey      # request.user; request.auth is the ApiKey
def issue_api_key(org: Org, name: str, raw: str | None = None) -> tuple[ApiKey, str]
def authenticate_key(raw: str) -> ApiKey | None
def revoke_api_key(key: ApiKey) -> None

# atlas/core/models.py
class OrgScopedQuerySet(QuerySet): def for_org(self, org) -> QuerySet

# atlas/core/exceptions.py
class Conflict(APIException)            # 409 "conflict"
def api_exception_handler(exc, context)  # REST_FRAMEWORK["EXCEPTION_HANDLER"]

# atlas/core/logging.py
def get_logger(name: str) -> logging.Logger
def redact(text: str) -> str
```

### 4.2 api (`atlas/api/`, `atlas/assets/filters.py`, `atlas/assets/ownership.py`)

Modules: `urls.py` (a `SimpleRouter`, mounted at `/api/v1/`), `views.py`,
`serializers.py`, `scoping.py` (`OrgScopedViewSetMixin`: `get_queryset()`
starts from `Model.objects.for_org(request.user.org)`, `perform_create()`
sets `org`), `pagination.py`, `throttling.py`.

| Endpoint | Methods | Notes |
|---|---|---|
| `/api/v1/assets/` | GET, POST | filters below; POST `{kind, key, label?, tags?}` normalizes `key` with `merge.identity.identity_key`, 409 if it exists (a `host` and a `domain` share one hostname, `identity_kinds`), source `api` |
| `/api/v1/assets/{id}/` | GET, PATCH, DELETE | PATCH `label`, `owner_team` (sets `owner_locked`; `""` clears the lock), `tags` (names); DELETE archives (204) and runs `evaluate_assets` on the asset, which resolves its open exposures |
| `/api/v1/assets/{id}/changes/` | GET | history, newest first |
| `/api/v1/tags/` | GET, POST, DELETE | |
| `/api/v1/ownership-rules/` | GET, POST, PATCH, DELETE | `POST /api/v1/ownership-rules/apply/` re-applies all rules |
| `/api/v1/exposures/` | GET | `status`, `rule`, `severity`, `asset` filters; read-only |
| `/api/v1/webhooks/` | GET, POST, PATCH, DELETE | `secret` is write-only; generated `DEMO-whsec-<slug>-<12 hex>` if omitted and returned once in the POST response |
| `/api/v1/saved-views/` | GET, POST, DELETE | `querystring` stored canonical (`canonical_querystring`) |

API writes record `AssetChange` rows (source `api`) but publish no webhooks:
only the worker's jobs call `notify.outbox`. Webhook URLs are validated with
`notify.delivery.host_allowed`, the check delivery repeats before every POST.

Asset JSON: `id, kind, key, label, owner_team, owner_locked, tags (names),
attributes, first_seen_at, last_seen_at, archived_at, open_exposures (count)`;
detail adds `sources` (`source_kind, source_name, first_seen_at,
last_seen_at`), `links`, `services`, `exposures`.

**Pagination.** `AssetCursorPagination(CursorPagination)`, ordering
`("-last_seen_at", "-id")`, `page_size` 50, `page_size` query param, max 500.
Body `{"next", "previous", "results"}` (cursor since 0.9, ADR 0003). The
changes list uses `("-occurred_at", "-id")`.

**Throttling.** `ApiKeyRateThrottle(SimpleRateThrottle)`, scope `api_key`
(`REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["api_key"]`, env `ATLAS_API_RATE`,
default `600/min`), keyed by `request.auth.pk`; set on every viewset.

```python
# atlas/assets/filters.py
FILTER_PARAMS = ("kind", "tag", "owner", "exposure", "changed_since", "changed_within", "q", "include_archived")
class InvalidFilter(ValueError): param: str
def filter_assets(queryset: QuerySet[Asset], params: Mapping[str, list[str]] | QueryDict, *, org: Org) -> QuerySet[Asset]
def canonical_querystring(params: Mapping[str, list[str]] | QueryDict) -> str
```
`kind` repeatable (any of); `tag` repeatable (all of); `owner=<team>` or
`owner=-` (unowned); `exposure=<rule>` or `any` (open exposures);
`changed_since=<ISO 8601 with offset>` (naive rejected); `changed_within=<hours>`
(uses `notify.changes.window_start`); `q` substring of key or label
(case-insensitive); archived assets hidden unless `include_archived=1`.
`canonical_querystring` keeps known params, drops empty values, sorts keys and
repeated values, URL-encodes. The API maps `InvalidFilter` to 400
`validation_failed` with `details = {param: [message]}`.

```python
# atlas/assets/ownership.py
def matching_rule(asset: Asset, rules: Sequence[OwnershipRule]) -> OwnershipRule | None
def apply_ownership(org: Org, asset_ids: Iterable[int] | None = None, *, job: Job | None = None) -> list[AssetChange]
```
Enabled rules in `(priority, id)` order, first match wins. `hostname`:
`fnmatch.fnmatchcase(asset.key, pattern)` for `host`/`domain` assets; `cidr`:
`ip` assets inside, `network` assets contained; `tag`: asset has the tag.
`owner_locked` assets are skipped. No match sets `owner_team = ""`. A
difference writes an `owner_changed` change. `asset_ids=None` means all assets
of the org.

### 4.3 importers (`atlas/importers/`)

Modules: `base.py`, `registry.py`, `zone_file.py`, `nimbus.py` (v1 and v2
exports), `ct_feed.py`, `port_scan.py`. Sample inputs in `fixtures/imports/`
(`zone/`, `nimbus/`, `ct/`, `scans/`).

```python
# atlas/importers/base.py
class ImportFormatError(ValueError)        # the whole file is unusable (permanent job failure)

@dataclass(frozen=True)
class ObservedLink:
    relation: str            # AssetLink.Relation value
    kind: str                # Asset.Kind of the target
    value: str               # target identity value (same rules as Observation.value)

@dataclass(frozen=True)
class ObservedService:
    port: int
    protocol: str = "tcp"
    service: str = ""
    product: str = ""
    banner: str = ""

@dataclass(frozen=True)
class Observation:
    kind: str                # Asset.Kind value
    value: str               # normalized: hostname / IP / CIDR via atlas.core.normalize,
                             # certificate SHA-256 hex, "nimbus:<account_id>:<resource_id>"
    label: str = ""
    attributes: dict = field(default_factory=dict)
    external_id: str = ""
    links: tuple[ObservedLink, ...] = ()
    services: tuple[ObservedService, ...] = ()

@dataclass
class ImportBatch:
    importer: str            # registry name
    source_kind: str         # AssetSource.Kind value
    source_name: str         # e.g. "harborview-bank.example.test zone", "nimbus account 4471-2210-0093"
    observed_at: datetime    # from the file when it says, else clock.now()
    observations: list[Observation]
    warnings: list[str] = field(default_factory=list)   # skipped records, human readable

# every importer module
def parse(text: str, *, source_name: str = "") -> ImportBatch

# atlas/importers/registry.py
IMPORTERS: dict[str, Callable[..., ImportBatch]]   # "zone_file", "nimbus", "ct_feed", "port_scan"
class UnknownImporter(KeyError)
def get_importer(name: str) -> Callable[..., ImportBatch]
```
Importers are pure: no database access. A record that cannot be read is
skipped with a warning; only a wholly unreadable file raises.

### 4.4 merge (`atlas/merge/`)

Modules: `identity.py`, `service.py`, `certificates.py`.

```python
# atlas/merge/identity.py
def identity_key(kind: str, value: str) -> str

# atlas/merge/certificates.py
def hostname_matches(pattern: str, hostname: str) -> bool   # "*.a.test" matches "x.a.test" only (one label)

# atlas/merge/service.py
@dataclass
class MergeResult:
    created: list[int]; updated: list[int]; unchanged: list[int]   # asset ids
    changes: list[AssetChange]
    @property
    def touched(self) -> list[int]   # created + updated + unchanged, in order

def merge_batch(org: Org, batch: ImportBatch, *, job: Job | None = None) -> MergeResult
```
Upserts assets by `(org, kind, identity_key)`, then `AssetSource` by
`(asset, source_kind, source_name)`. `first_seen_at` keeps the minimum,
`last_seen_at` the maximum of `batch.observed_at`. Label and attributes come
from the most recently seen source. Link targets are created when missing.
Certificates get `covers` links to every host of the org matched by a SAN.
A `port_scan` batch closes services of the scanned assets it no longer
reports. An archived asset seen again is restored (`archived_at` cleared,
an `updated` change with `field = "archived_at"`), but only by a batch whose
`observed_at` is not older than `archived_at`. A hostname is one asset across
`domain` and `host` (`identity.identity_kinds`): a `host` observation or link
target reuses the `domain` of that name, and a direct `domain` observation
turns an existing `host` into the domain (`updated`, `field = "kind"`), so the
CT feed's apex SAN and the zone apex are one asset in any import order.
Nothing is ever removed: links and sources stay, and an asset missing from a
later snapshot is neither archived nor closed (services excepted: see the
port-scan rule above). Every difference writes an `AssetChange` with `job`.
Runs inside the caller's transaction and needs one: it starts with
`SELECT ... FOR UPDATE` on the org row, so two imports of one org merge one
after the other.

### 4.5 jobs (`atlas/jobs/`)

```python
# atlas/jobs/queue.py
def enqueue(org: Org, kind: str, payload: dict, *, run_after: datetime | None = None,
            max_attempts: int | None = None) -> Job          # default settings.ATLAS_JOB_MAX_ATTEMPTS
def claim(worker_id: str) -> Job | None   # own transaction; status queued|failed, run_after <= now,
                                          # ORDER BY run_after, id, FOR UPDATE SKIP LOCKED
def complete(job: Job, result: dict) -> None
def fail(job: Job, error: str, *, permanent: bool = False) -> None
def backoff_seconds(attempts: int) -> int     # min(10 * 2 ** (attempts - 1), 600)

# atlas/jobs/handlers.py
class PermanentJobError(Exception)
HANDLERS: dict[str, Callable[[Job], dict]]   # returns Job.result

# atlas/jobs/worker.py
def run_once(worker_id: str) -> bool          # True if a job ran; then deliver_due()
def run_forever(worker_id: str, *, poll_seconds: float) -> None
```
Commands: `run_worker [--once] [--worker-id ID]`, `enqueue_import --org SLUG
--importer NAME --path RELATIVE [--source-name NAME]`.

| Kind | Payload | Result |
|---|---|---|
| `import.run` | `{"importer": "zone_file"\|"nimbus"\|"ct_feed"\|"port_scan", "path": "<relative to ATLAS_IMPORT_ROOT>", "source_name": "<optional>"}` | `{"importer", "source_name", "observations", "created", "updated", "unchanged", "warnings", "exposures_opened", "exposures_resolved", "events"}` |
| `exposure.evaluate` | `{"asset_ids": [int, ...] \| null}` (null = all assets) | `{"evaluated", "opened", "resolved", "events"}` |

`fail()`: `dead` when `permanent` (`PermanentJobError`, `ImportFormatError`,
`UnknownImporter`) or `attempts >= max_attempts`, else `failed` with
`run_after = now + backoff_seconds(attempts)`. The handler and `complete()`
commit together; `fail()` runs in a fresh transaction after the rollback.

### 4.6 exposure (`atlas/exposure/`)

```python
# atlas/exposure/rules.py
@dataclass(frozen=True)
class RuleContext:
    org: Org
    now: datetime
    today: date              # clock.local_date(org.timezone, now)
    @classmethod
    def for_org(cls, org, now=None) -> RuleContext

@dataclass(frozen=True)
class Hit:
    subject: str; severity: str; title: str; details: dict

RULES: dict[str, Callable[[Asset, RuleContext], list[Hit]]]   # keys = Exposure.Rule values

# atlas/exposure/service.py
@dataclass
class EvaluationResult:
    opened: list[Exposure]; resolved: list[Exposure]; changes: list[AssetChange]
    evaluated: int           # assets looked at

def evaluate_assets(org: Org, asset_ids: Iterable[int] | None = None, *, job: Job | None = None) -> EvaluationResult
```

| Rule | Applies to | Fires when | Severity | Subject |
|---|---|---|---|---|
| `admin_panel_public` | `ip` assets | public (`is_public_ip`) with an open service whose service/product/banner looks like an admin UI | high | `"<port>/<protocol>"` |
| `cert_expiring` | `certificate` | `not_after` date (org timezone) minus `today` <= `org.cert_warning_days`; critical once expired | medium / critical | `""` |
| `dangling_cname` | `host` | a `cname` target host has no `resolves_to` and no `cname` link of its own | high | target key |
| `unexpected_port` | `ip` | public, open service with a port not in `org.allowed_ports` | medium | `"<port>/<protocol>"` |

A hit with no open exposure opens one (`exposure_opened` change); an open
exposure still hit gets `last_evaluated_at` (and severity/title/details)
refreshed; an open exposure no longer hit, or on an archived asset, is
resolved (`exposure_resolved` change). Runs inside the caller's transaction.

### 4.7 notify (`atlas/notify/`, `mockhook/`)

```python
# atlas/notify/changes.py
def window_start(org: Org, hours: int = 24, *, now: datetime | None = None) -> datetime
    # elapsed time: now - timedelta(hours=hours), whatever the org's DST
def changed_asset_ids(org: Org, since: datetime) -> QuerySet   # values_list("asset_id") of changes >= since

# atlas/notify/outbox.py
def enqueue(org: Org, event: str, data: dict) -> list[OutboxEvent]
    # one row per enabled webhook of the org subscribed to event; caller's transaction
def publish_changes(org: Org, changes: Sequence[AssetChange]) -> list[OutboxEvent]
def group_changes(org: Org, changes) -> list[tuple[str, dict]]   # (event, data), used by publish_changes

# atlas/notify/signing.py
def sign(secret: str, body: bytes, timestamp: int) -> str     # "t=<timestamp>,v1=<hex>"
def verify(secret: str, body: bytes, header: str, *, now: int, tolerance: int = 300) -> bool
def parse_header(header: str) -> tuple[int, list[str]]       # (t, [v1 signatures])

# atlas/notify/delivery.py
def build_body(event: OutboxEvent) -> bytes
def backoff_seconds(attempts: int) -> int     # min(30 * 2 ** (attempts - 1), 3600)
def host_allowed(url: str) -> bool            # settings.ATLAS_WEBHOOK_ALLOWED_HOSTS (fnmatch), [] = any
def deliver_due(*, limit: int = 50) -> int    # rows attempted
```
`publish_changes` groups by asset: an asset with a `created` change gives one
`asset.created` (its other non-exposure changes ride along in it); otherwise
non-exposure changes give one `asset.changed`; every `exposure_opened` /
`exposure_resolved` gives one `exposure.opened` / `exposure.resolved`.

`deliver_due` locks due rows (`pending`/`failed`, `next_attempt_at <= now`)
with `FOR UPDATE SKIP LOCKED`, POSTs with `urllib` (timeout
`ATLAS_WEBHOOK_TIMEOUT_SECONDS`), 2xx -> `delivered`; anything else ->
`attempts + 1`, `failed` with `next_attempt_at = now + backoff_seconds`, or
`dead` at `ATLAS_WEBHOOK_MAX_ATTEMPTS` (8). A URL failing `host_allowed` goes
`dead` at once with `last_error = "blocked host"`; a row whose webhook was
disabled after it was written goes `dead` with `"webhook disabled"`. Each row
stays locked in its own transaction during its POST, so delivery is
at-least-once: receivers dedupe on `X-Atlas-Delivery`. `jobs.worker.run_once`
calls `deliver_due()` after every iteration, job or not.

`mockhook` (`python -m mockhook`, stdlib `http.server`, port `MOCKHOOK_PORT`
9000): `POST /hooks/<name>` appends one JSON line to `MOCKHOOK_LOG`
(`received_at`, `path`, `event`, `delivery`, `signature`, `body`, and
`signature_ok` when `MOCKHOOK_SECRET` is set) and answers 200 (401 on a bad
signature when a secret is set); `GET /hooks` returns the last 50 lines.
`MOCKHOOK_SECRET` is one secret, so with it set only the org whose webhook
uses that secret verifies; compose leaves it empty. mockhook follows
`ATLAS_NOW` for its timestamp check.

### 4.8 dashboard (`atlas/dashboard/`)

`urls.py` mounted at `/`; `views.py`; `context.py` (`current_org`);
`charts.py` (`bar_chart`: inline-SVG bars for the exposures page);
`csv_export.py` (`asset_rows`: CSV lines through `iterator()`, cells starting
with `= + - @` prefixed with `'`); templates in `templates/dashboard/` and
`templates/registration/login.html`; static in `static/dashboard/`
(`atlas.css`, `atlas.js`). Login uses `django.contrib.auth.urls` at
`/accounts/`.

| URL | View | Notes |
|---|---|---|
| `/` | redirect to `/assets/` | |
| `/assets/` | asset list | filters = `filter_assets` params, 50 per page, saved views, "changed in last 24h" = `changed_within=24` |
| `/assets.csv` | CSV of the current filtered list | `StreamingHttpResponse` |
| `/assets/<id>/` | detail | sources, links, services, exposures, history (last 200) |
| `/exposures/` | exposures overview | open exposures by severity (SVG chart) and rule, 50 most recent |
| `/ownership/` | ownership rules (function-based) | |
| `/views/` | save / delete saved views | POST |

`current_org(request) -> Org` (`atlas/dashboard/context.py`): the org chosen
with `?org=<slug>` (kept in the session) among the user's memberships, else
the remembered one if the user is still a member, else the lowest org id;
404 when `?org=` names an org the user is not a member of, or the user has no
membership. Saved views: the list shows the user's own views plus the org's
shared ones (`owner` NULL, created through the API); only your own can be
deleted. `Membership.role` is stored but not enforced anywhere yet. A bad
filter renders the list with an error message (200); the CSV answers 400
with plain text.

### 4.9 seed and bench

`python manage.py seed [--seed 42] [--scale N] [--reset]`: deterministic,
refuses when orgs exist unless `--reset`; the orgs, API keys and webhooks of
§9; ~5,000 assets with sources, links, services, tags, ownership rules,
exposures and 8 weeks of history ending at 2026-11-05T14:30Z; `--scale`
multiplies asset volume (Quillstone ~40k at `--scale 8`). Rows are written
directly (no importers, no merge, no outbox rows, so no webhooks); then the
real `apply_ownership` and `evaluate_assets` run once per org at the anchor
inside the seed's transaction, so owners and open exposures are exactly what
the code computes (the output's `rule_fixes` counts what they corrected,
a handful at most). `python manage.py
create_demo_user`: user `demo`, password `DEMO-atlas-demo`, member of all
three orgs, idempotent. `scripts/bench.py` times the API search and the
dashboard list on seeded data.

## 5. Webhooks

Events: `asset.created`, `asset.changed`, `exposure.opened`,
`exposure.resolved`, `import.completed` (`atlas.notify.models.EVENTS`).

Body (built at delivery time; `payload` holds `data`):

```json
{"id": "evt_123", "event": "exposure.opened", "org": "harborview-bank",
 "occurred_at": "2026-11-05T14:30:00Z", "data": {...}}
```

`occurred_at` is the outbox row's `created_at`. `data` by event:
`asset.created` `{"asset": A, "changes": [C...]}`; `asset.changed`
`{"asset": A, "changes": [C...]}`; `exposure.*` `{"asset": A, "exposure":
{"id", "rule", "subject", "severity", "title", "opened_at", "resolved_at"}}`;
`import.completed` `{"job_id", "importer", "source_name", "created",
"updated", "unchanged", "exposures_opened", "exposures_resolved"}`, where
`A = {"id", "kind", "key", "label", "owner_team"}` and `C = {"kind", "field",
"old", "new"}`.

Headers: `Content-Type: application/json`, `X-Atlas-Event`,
`X-Atlas-Delivery: <outbox id>`, `X-Atlas-Signature: t=<unix seconds>,v1=<hex>`
where `hex = HMAC-SHA256(secret, f"{t}.".encode() + body)`. Receivers
should reject timestamps older than 300 s and compare in constant time.

## 6. API errors

Every error is `{"error": {"code": str, "message": str, "details": object | null}}`.

| Status | Code | When |
|---|---|---|
| 400 | `validation_failed` | serializer/filter errors (`details` = field -> messages), `NormalizationError` |
| 400 | `parse_error` | malformed JSON |
| 401 | `unauthenticated` | missing, malformed, unknown or revoked key |
| 403 | `forbidden` | |
| 404 | `not_found` | missing **or another org's** object |
| 405 | `method_not_allowed` | |
| 409 | `conflict` | `atlas.core.exceptions.Conflict` (duplicate asset, tag, view name) |
| 429 | `throttled` | `Retry-After` header, `details.retry_after_seconds` |

## 7. Conventions

- **Clock.** Use `atlas.core.clock.now()`, never `timezone.now()` /
  `datetime.now()`. Store UTC; convert to `org.timezone` only for "today" and
  display (`clock.local_date`). Model defaults already use `clock.now`.
- **Org scoping.** Every query on customer data starts with
  `Model.objects.for_org(org)`. The org comes from `request.user.org` (API),
  `current_org(request)` (dashboard) or `job.org` (worker), never from a
  request parameter or body. Another org's id answers 404.
- **Transactions.** No `ATOMIC_REQUESTS`; views that write several rows use
  `transaction.atomic()`. Service functions (`merge_batch`,
  `apply_ownership`, `evaluate_assets`, `publish_changes`, `enqueue`) never
  commit: they run inside the caller's transaction. Only `jobs.queue.claim`
  and `fail`, the worker loop (`jobs.worker.execute`: handler + `complete`
  in one block, not the handler itself) and `notify.delivery.deliver_due`
  own transactions.
- **Logging.** `logger = get_logger(__name__)`; message = dotted event name
  (`import.completed`, `webhook.failed`), details in `extra`. Never log raw
  API keys, webhook secrets or request headers; the formatters redact the
  known shapes as a last line of defence.
- **Errors.** Raise DRF exceptions or `Conflict` in the API; the handler
  shapes the body. Domain code raises `ValueError` subclasses
  (`NormalizationError`, `ImportFormatError`, `InvalidFilter`).
- **Tests.** `tests/<component>/` with an `__init__.py`. Shared fixtures in
  `tests/conftest.py`: `frozen_clock` (autouse, 2026-11-05T14:30Z;
  `frozen_clock.advance(hours=25)`), `org` (harborview-bank), `other_org`
  (quillstone-media), `api_client` / `other_api_client` (DRF `APIClient`
  with a valid key), `dashboard_user`, `dashboard_client`; plus pytest-django
  `db`, `client`, `settings`, `django_capture_on_commit_callbacks`. Factories
  in `tests/factories.py`: `TODAY`, `ORGS`, `make_org`, `make_api_key`
  (returns `(key, raw)`), `make_user(username, orgs=...)`, `make_asset`,
  `make_source`, `make_link`, `make_service`, `make_tag`, `make_rule`,
  `make_change`, `make_exposure`, `make_webhook`, `make_outbox`, `make_job`,
  `make_saved_view`. Tests needing two connections (`skip_locked`) use
  `@pytest.mark.django_db(transaction=True)`.

## 8. Settings

`atlas.settings.base` (shared), `.dev` (compose, `DEBUG`), `.test` (pytest).
Environment: `ATLAS_DB_*`, `ATLAS_LOG_FORMAT` (`json`/`text`),
`ATLAS_LOG_LEVEL`, `ATLAS_API_RATE`, `ATLAS_IMPORT_ROOT`
(default `fixtures/imports`), `ATLAS_JOB_MAX_ATTEMPTS` (5),
`ATLAS_WORKER_POLL_SECONDS` (1.0), `ATLAS_WEBHOOK_TIMEOUT_SECONDS` (5),
`ATLAS_WEBHOOK_MAX_ATTEMPTS` (8), `ATLAS_WEBHOOK_ALLOWED_HOSTS`
(`mockhook,localhost,*.example.test`; empty = any), `ATLAS_PORT` (host port,
compose only), `ATLAS_NOW` (dev settings only: the clock of each process
starts at this instant and runs on; compose defaults it to the seed anchor
`2026-11-05T14:30:00Z`, `ATLAS_NOW=` gives the real clock; tests and the seed
freeze the clock and ignore it), `MOCKHOOK_SECRET` (mockhook only).

## 9. Demo data

| Org | Domain | Timezone | Allowed ports | API key (DEMO) | Webhook secret (DEMO) |
|---|---|---|---|---|---|
| `harborview-bank` Harborview Bank | `harborview-bank.example.test` | America/Toronto | 443 | `atl_DEMO_k5lv9z8g76x8az3c8x0ajrk98pwkji8f` | `DEMO-whsec-harborview-bank-e33d70005377` |
| `quillstone-media` Quillstone Media | `quillstone-media.example.test` | Europe/London | 80, 443 | `atl_DEMO_lk3derxtk5a6cyct4gpy0cv4d8mbeooy` | `DEMO-whsec-quillstone-media-a193907f8b4b` |
| `orchid-grid` Orchid Grid | `orchid-grid.example.test` | Pacific/Auckland | 22, 443, 8443 | `atl_DEMO_k8p4pxiky19mehziqutg5ri41pvcx876` | `DEMO-whsec-orchid-grid-3897bfee30d5` |

Webhooks point at `http://mockhook:9000/hooks/<slug>`. Public addresses in
fixtures and the seed come from the documentation ranges (`192.0.2.0/24`,
`198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), which
`is_public_ip` treats as public; internal ones from `10.0.0.0/8`.
