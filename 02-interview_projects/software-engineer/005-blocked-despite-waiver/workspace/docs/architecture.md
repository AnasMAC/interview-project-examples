# Gatekeeper architecture

Owner: Grace Adeyemi (platform security). Last reviewed for 3.6.0.

Gatekeeper is the release gate every Mossbank CI pipeline calls before a
deploy. A pipeline posts build evidence; Gatekeeper evaluates the team's
current policy, applies approved waivers and answers **pass**, **warn** or
**block** with reasons. The decision is stored, audited and, when the pipeline
asked for it, sent back to the CI system as a signed callback.

This page is the contract between the packages. If you change a table, a
function signature, an error code or a payload listed here, change this page
in the same pull request.

Contents: 1 Processes · 2 Packages and owners · 3 Data model · 4 Request flow ·
5 Evidence · 6 Policy DSL (summary) · 7 Decision model · 8 Waivers ·
9 Audit · 10 Callbacks and outbox · 11 Scheduler · 12 HTTP API conventions
and error model · 13 Cross-cutting conventions · 14 Test helpers ·
15 Seeded data contract

## 1. Processes

| Compose service | Command | Role |
|---|---|---|
| `app` | `gunicorn 'gatekeeper.core.app:create_app()'` (2 workers, port 8000, published on `127.0.0.1:${GATE_PORT:-8090}`) | HTTP API |
| `scheduler` | `python -m gatekeeper.scheduler` | waiver expiry, expiry notices, callback delivery; one active instance (advisory lock) |
| `ci-mock` | `python -m ci_mock` (port 9100, compose network only) | stands in for Forgeline CI; logs every callback to `var/ci-mock/callbacks.jsonl` |
| `db` | `postgres:16.4-alpine` | `gatekeeper` (dev) and `gatekeeper_test` (tests) |
| `tests` (profile) | `pytest` | test runner against `gatekeeper_test` |

## 2. Packages and owners

| Path | Owner | Responsibility |
|---|---|---|
| `gatekeeper/core/` | Grace Adeyemi | config, app factory, engine + tables, transactions, clock, errors, auth, logging, shared value types |
| `migrations/` | Grace Adeyemi | Alembic revisions (`0001` 1.0.0, `0002` 2.0.0, `0003` 3.1.0) |
| `gatekeeper/ingest/` | Tobias Krüger (legacy adapter: Ana Petrović) | `POST /v1/evaluations`, payload adapters, limits, idempotency, evidence storage |
| `gatekeeper/evaluation/` | Tobias Krüger | policy DSL, compiler + cache, rules, conditions, evaluator, policy versions, dry run |
| `gatekeeper/waivers/` | Mariana Silva | waiver requests and review, matching, expiry, expiry notices |
| `gatekeeper/audit/` | Mariana Silva | audit log writes and the read API |
| `gatekeeper/callbacks/`, `ci_mock/` | Kwame Boateng | outbox, HMAC signing, delivery and retries; local CI receiver |
| `gatekeeper/scheduler/` | Kwame Boateng | the single-runner loop |
| `gatekeeper/reporting/`, `scripts/bench.py` | Mariana Silva | scorecards, CSV export, benchmark |
| `gatekeeper/cli/`, `gatekeeper/seed/` | Grace Adeyemi | operator commands, deterministic demo data |

Module layout inside each package (public entry points in **bold**):

- ingest: **`api.py`** (`bp`), `schemas.py` (marshmallow + limits), **`adapters/__init__.py`** (`to_submission`), `adapters/forgeline_v2.py`, `adapters/legacy.py`, `idempotency.py`, **`service.py`**
- evaluation: **`api.py`** (`bp`), `schemas.py`, `dsl.py` (YAML -> `Policy`), `compiler.py` (`Policy` -> `CompiledPolicy`, per-version cache), `rules.py`, `conditions.py`, `evaluator.py` (results + aggregation), **`service.py`**
- waivers: **`api.py`** (`bp`), `schemas.py`, **`service.py`**, `matching.py`, `versions.py` (version ranges), **`expiry.py`**, **`notices.py`**
- audit: **`api.py`** (`bp`), **`service.py`**
- callbacks: **`service.py`**, **`signing.py`**, **`delivery.py`**; `ci_mock/__main__.py`
- scheduler: `__main__.py`, `runner.py` (lock + loop), `jobs.py`
- reporting: **`api.py`** (`bp`), **`queries.py`**, **`export.py`**
- cli: `__main__.py`, `commands.py` · seed: `__main__.py`, `generate.py`, `data.py`

Blueprints are registered by import path in `gatekeeper/core/app.py`
(`BLUEPRINTS`):

| Import path | Blueprint name | URL prefix |
|---|---|---|
| `gatekeeper.core.app:core_bp` | `core` | none (`/healthz`, `/v1/whoami`) |
| `gatekeeper.ingest.api:bp` | `ingest` | `/v1/evaluations` |
| `gatekeeper.evaluation.api:bp` | `policies` | `/v1/policies` |
| `gatekeeper.waivers.api:bp` | `waivers` | `/v1/waivers` |
| `gatekeeper.audit.api:bp` | `audit` | `/v1/audit` |
| `gatekeeper.reporting.api:bp` | `reports` | `/v1/reports` |

Callbacks, scheduler, cli and seed have no blueprint.

## 3. Data model

Defined once in `gatekeeper/core/tables.py` (SQLAlchemy Core `Table`s, ADR
0001) and created by `migrations/versions/`. All timestamps are `timestamptz`
written from `clock.now()`. Ids are serial integers (`bigint` for the high
volume tables).

**teams** `id`, `slug` (unique, e.g. `payments-api`), `name`, `timezone` (IANA,
default `Europe/London`), `callback_secret` (HMAC key for callbacks,
`DEMO-whsec-<slug>-<12 hex>`), `notify_url` (where `waiver.expiring` notices go;
nullable), `created_at`.

**services** `id`, `team_id`, `slug` (unique per team), `name`, `created_at`.
A service must exist before CI can evaluate it (CLI or seed creates them).

**api_keys** `id`, `team_id` (null for reviewers), `name` (label shown in audit
as `key:<name>`), `role` (`team` | `security_reviewer`; check constraint: team
keys have a team, reviewer keys have none), `prefix` (first 16 characters,
unique), `key_hash` (sha256 hex of the full key), `created_at`, `revoked_at`.

**policies** `id`, `team_id`, `version` (1, 2, ... per team; unique
`(team_id, version)`), `source` (the YAML as submitted), `comment`,
`created_by`, `created_at`. The **active policy** of a team is its highest
version. Rows are never updated or deleted (ADR 0002).

**evaluations** `id`, `team_id`, `service_id`, `policy_id` (null when the team
had no policy), `source` (`forgeline_v2` | `legacy`), `pipeline_id`,
`commit_sha`, `branch`, `environment` (`production` | `staging` |
`development`), `version` (release version, nullable), `decision` (`pass` |
`warn` | `block`), `reasons` (JSONB list, section 7), `callback_url`,
`idempotency_key`, `payload_sha256`, `created_at`. Unique
`(team_id, idempotency_key)` where the key is not null. Indexes
`(team_id, created_at)`, `(service_id, created_at)`.

**evidence** `id`, `evaluation_id` (cascade delete), `kind` (section 5),
`data` (JSONB, normalized shape), unique `(evaluation_id, kind)`.

**waivers** `id`, `team_id`, `service_id` (null = every service of the team),
`rule` (canonical rule id), `version_range` (nullable, section 8), `reason`,
`requested_by`, `status` (`pending` | `approved` | `rejected` | `revoked` |
`expired`), `reviewed_by`, `reviewed_at`, `review_note`, `expires_at`,
`expiry_notice_sent_at`, `created_at`.

**audit_events** `id`, `team_id` (nullable), `actor`, `action`,
`subject_type`, `subject_id`, `details` (JSONB), `created_at`. Append only.

**callback_outbox** `id`, `team_id`, `evaluation_id` (nullable), `event`,
`url`, `payload` (JSONB), `status` (`pending` | `delivered` | `dead`),
`attempts`, `next_attempt_at`, `last_error`, `created_at`, `delivered_at`.
Partial index on `next_attempt_at` where `status = 'pending'`.

**scheduler_runs** `job` (primary key), `last_started_at`, `last_finished_at`,
`last_status` (`ok` | `error`), `last_error`, `runs`.

Migration history: `0001` (1.0.0) teams, services, keys, policies,
evaluations, evidence, audit; `0002` (2.0.0) waivers, outbox,
`teams.callback_secret` (backfilled for existing teams) and `notify_url`,
`evaluations.callback_url`; `0003` (3.1.0) idempotency columns and index,
`waivers.version_range` and `expiry_notice_sent_at`, `scheduler_runs`. A new
revision is `0004_<slug>.py` with `down_revision = "0003"`; update
`tables.py` in the same change (`tests/core/test_db.py` compares them).

## 4. Request flow: `POST /v1/evaluations`

```
CI --POST--> ingest.api.create_evaluation           (team key only; 403 role_required for reviewers)
              |  raw JSON <= GATE_MAX_PAYLOAD_BYTES (413 payload_too_large)
              |  ingest.adapters.to_submission(payload) -> Submission  (422 on invalid / too large)
              |  with transaction() as conn:
              |     ingest.service.submit(conn, principal, submission, idempotency_key, payload_sha256)
              |        idempotency check (same key+hash -> stored evaluation, 200; different hash -> 409)
              |        service lookup by slug within the team (422 unknown_service)
              |        evaluation.service.evaluate(conn, team_id, service_id, submission) -> Decision
              |            -> waivers.service.apply_waivers(...)
              |        insert evaluations + evidence rows
              |        audit.service.record("evaluation.decided"), one "waiver.applied" per waived result
              |        callbacks.service.enqueue("evaluation.decided") when callback_url is set
              |  201 + evaluation view
scheduler --> callbacks.delivery.deliver_due() --signed POST--> CI (ci-mock locally)
```

Everything inside `submit` is one transaction: a decision is never stored
without its audit event and outbox row.

Public functions (keyword-only after `conn`):

```python
# gatekeeper/ingest/adapters/__init__.py
def to_submission(payload: dict[str, Any]) -> Submission
    # "schema" == "forgeline/v2" -> forgeline_v2.to_submission
    # "runner" starting with "legacy-runner/" -> legacy.to_submission
    # anything else -> ValidationFailed(code="unknown_payload_format")

# gatekeeper/ingest/idempotency.py
def payload_sha256(payload: dict[str, Any]) -> str
    # sha256 hex of json.dumps(payload, sort_keys=True, separators=(",", ":"))

# gatekeeper/ingest/service.py
def submit(conn, *, principal: Principal, submission: Submission,
           idempotency_key: str | None, payload_sha256: str) -> tuple[dict[str, Any], bool]
    # (evaluation view, created); created is False for an idempotent replay
def evaluation_view(conn, evaluation_id: int) -> dict[str, Any]
def list_evaluations(conn, *, team_id: int | None, service: str | None = None,
                     decision: str | None = None, branch: str | None = None,
                     limit: int, offset: int) -> tuple[list[dict[str, Any]], int]
# gatekeeper/ingest/idempotency.py (also)
def parse_key(raw: str | None) -> str | None             # 400 invalid_idempotency_key
def find_replay(conn, *, team_id: int, key: str, payload_sha256: str) -> int | None  # 409

# gatekeeper/evaluation/service.py
def evaluate(conn, *, team_id: int, service_id: int, submission: Submission) -> Decision
def publish_policy(conn, *, team_id: int, source: str, actor: str,
                   comment: str | None = None) -> dict[str, Any]
    # validates (ValidationFailed code="invalid_policy"), inserts max(version)+1,
    # records audit "policy.published"; returns the policy view
def dry_run(conn, *, team_id: int, service_id: int, submission: Submission,
            source: str | None = None) -> Decision
    # source None = active policy; reads waivers, writes nothing
def active_policy(conn, team_id: int) -> Row | None
def get_policy(conn, *, team_id: int, version: int) -> dict[str, Any]       # 404
def list_policies(conn, *, team_id: int | None, limit: int, offset: int
                  ) -> tuple[list[dict[str, Any]], int]
def service_id_for(conn, *, team_id: int, slug: str) -> int                 # 422 unknown_service
```

`evaluate` only calls `apply_waivers` when at least one result is `warn` or
`block`; it never writes. Policies are compiled once per `(team_id, version)`
in a per-process LRU cache (`compiler.PolicyCache`, 256 entries); an entry is
reused only if the row's id and source are the ones it was compiled from.
`publish_policy` calls `compiler.invalidate_team`, which frees only the
publishing worker's entries: other gunicorn workers pick the new version up
because `evaluate` reads the active version from the database first. A stored
policy that no longer parses makes `evaluate` raise 422 `invalid_policy`.

Evaluation view (response of `POST`/`GET /v1/evaluations/<id>` and the
`evaluation` field of the callback):

```json
{"id": 8123, "team": "payments-api", "service": "payments-api", "source": "forgeline_v2",
 "pipeline_id": "fl-88213", "commit_sha": "9f2c...", "branch": "main",
 "environment": "production", "version": "4.12.0", "decision": "block",
 "reasons": [ ...section 7... ], "policy_version": 7,
 "created_at": "2026-12-02T10:58:11+00:00"}
```

Idempotency: header `Idempotency-Key` (1 to 128 characters of
`[A-Za-z0-9._:-]`, else 400 `invalid_idempotency_key`). Same key and same
`payload_sha256` within the team: 200 with the stored evaluation and header
`Idempotent-Replay: true`, no new audit event, evidence or callback. Same key
and different hash: 409 `idempotency_conflict` with `details.evaluation_id`.
Two concurrent first requests race on the unique index; the loser re-reads
and answers as a replay.

Other ingest routes: `GET /v1/evaluations/<id>` (404 for another team's
evaluation), `GET /v1/evaluations?service=&decision=&branch=&limit=&offset=`
(reviewers add `team=`), newest first; a `decision` other than pass, warn or
block is 400 `bad_request`. `created_at` in the view is UTC, truncated to
seconds. Every stored evaluation with a callback URL gets its own outbox row
(no de-duplication across pipelines); an idempotent replay gets none.

## 5. Evidence

`Submission` (in `gatekeeper/core/contracts.py`) carries normalized evidence:
`evidence: dict[kind, data]`. Kinds are `EVIDENCE_KINDS`; a kind the pipeline
did not send is absent. Severities are `SEVERITIES` = `none`, `low`,
`medium`, `high`, `critical` (`severity_rank()` gives 0..4).

| kind | normalized `data` |
|---|---|
| `dependencies` | `{"packages": [{"name", "version", "ecosystem", "vulnerabilities": [{"id", "severity"}]}]}` |
| `secrets` | `{"count": int, "findings": [{"detector", "path", "line"}]}` (`count >= len(findings)`; the legacy runner only sends a count) |
| `sast` | `{"new": {"critical", "high", "medium", "low"}, "total": {same} or null}` |
| `tests` | `{"passed": int, "failed": int, "skipped": int}` |
| `signing` | `{"signed": bool, "verified": bool, "key_id": str or null}` |

**Forgeline CI payload v2** (`schema: forgeline/v2`):

```json
{
  "schema": "forgeline/v2",
  "pipeline": {"id": "fl-88213", "url": "https://forgeline.mossbank.example.test/runs/88213"},
  "project": {"service": "payments-api"},
  "git": {"sha": "9f2c4e1d...", "ref": "refs/heads/main"},
  "deploy": {"environment": "production", "version": "4.12.0"},
  "callback": {"url": "http://ci-mock:9100/callbacks/payments-api/payments-api"},
  "evidence": {
    "dependencies": [{"name": "ledgerkit", "version": "2.4.1", "ecosystem": "pypi",
                      "advisories": [{"id": "MBSA-2026-0141", "severity": "HIGH"}]}],
    "secrets_scan": {"findings": [{"detector": "generic-api-key", "file": "deploy/app.env", "line": 3}]},
    "sast": {"new_findings": {"critical": 0, "high": 1, "medium": 2, "low": 0},
             "total_findings": {"critical": 0, "high": 4, "medium": 19, "low": 40}},
    "tests": {"passed": 412, "failed": 0, "skipped": 6},
    "signing": {"signed": true, "verified": true, "key_id": "mossbank-release-2026"}
  }
}
```

Mapping: `git.ref` `refs/heads/<b>` -> branch `<b>`, `refs/tags/<t>` -> `<t>`;
any other `refs/...` (e.g. `refs/pull/12/head`) is 422 `validation_failed`, a
bare name is used as is; severities are upper case on the wire (any case is
accepted) and lower case in evidence; `secrets_scan` -> `secrets` with
`count = len(findings)`; `callback` optional; unknown fields are ignored
(Forgeline adds fields between minor releases).

**Legacy runner payload** (`runner: legacy-runner/1.x`, flat):

```json
{"runner": "legacy-runner/1.8", "service_name": "kyc-api", "build_id": "LR-20261202-0042",
 "git_commit": "4be1...", "git_branch": "main", "deploy_env": "prod", "app_version": "2.3.1",
 "callback": "http://ci-mock:9100/callbacks/kyc-platform/kyc-api",
 "vulns": [{"package": "pdfmint", "installed": "0.9.2", "id": "MBSA-2025-0310", "sev": "MODERATE"}],
 "secrets_found": 0, "sast_crit_new": 0, "sast_high_new": 1, "sast_medium_new": 3,
 "tests_total": 120, "tests_failed": 2, "tests_skipped": 0, "signed": "yes"}
```

Mapping: `deploy_env` `prod`/`stg`/`dev` -> `production`/`staging`/`development`;
`passed = tests_total - tests_failed - tests_skipped`; `verified = signed`;
`sast.total = null`; `ecosystem` is `"unknown"` unless a vuln names one; vulns
of the same package and version are grouped; severities (case-insensitive, trimmed): `CRITICAL CRIT
SEV1 P1` -> critical, `HIGH IMPORTANT SEV2 P2` -> high, `MEDIUM MODERATE MED
SEV3 P3` -> medium, `LOW MINOR SEV4 P4` -> low, `NONE INFO INFORMATIONAL
NEGLIGIBLE` and empty -> none; anything else -> **high** with a
`ingest.legacy_unknown_severity` warning.

Limits (422 `evidence_too_large`, `details.limit`): 5,000 packages, 200
vulnerabilities per package, 1,000 secret findings (counted on the normalized
evidence, whichever adapter); any string anywhere in the payload at most 512
characters (`details.path`, checked before the adapter runs); the body at most
`GATE_MAX_PAYLOAD_BYTES` (1 MiB, 413). `deploy.version` is at most 64
characters.

## 6. Policy DSL (summary; full reference in `docs/policy-dsl.md`)

```yaml
policy: 1
rules:
  - id: dependency.max_severity     # highest allowed severity, inclusive
    max: high
    action: block                   # block (default) | warn
  - id: secrets.allowed             # allowed secret findings
    max: 0
  - id: sast.new_high_max           # allowed new high + critical SAST findings
    max: 0
    action: warn
  - id: tests.min_pass_rate         # passed / (passed + failed), skipped excluded
    min: 0.95
  - id: signing.required            # signed and verified
    when:
      branches: ["main", "release/*"]   # fnmatch globs, any match
      environments: [production]        # any of
```

A rule whose `when` does not match the submission is skipped (no result). A
rule whose evidence kind is missing produces its `action` with
`details.missing = true`. `sast.max_high` is accepted as a deprecated alias of
`sast.new_high_max` (3.2). Unknown keys are an `invalid_policy` error.

Details the reference page does not spell out (`evaluation/dsl.py`,
`rules.py`, `conditions.py`):

- Defaults: `action: block`; `secrets.allowed` and `sast.new_high_max` `max: 0`;
  `dependency.max_severity` `max` and `tests.min_pass_rate` `min` are required.
- Each rule at most once, aliases included: `sast.max_high` plus
  `sast.new_high_max` in one policy is a duplicate. Publishing with the alias
  succeeds and the response's `warnings` lists it.
- `when.environments` accepts `prod`, `stg`, `dev` (3.3) and stores the
  canonical names; an unknown name or an empty list is an error.
  `when.branches` uses `fnmatchcase`, so `*` also crosses `/`.
- `tests.min_pass_rate`: no executed test (`passed + failed == 0`) fails
  unless `min` is 0.
- `dependency.max_severity` details list at most 50 violations (`count` has
  the full number); the message names the worst one plus "and N more".
- Documents over 64 KiB, YAML that is not a mapping, `policy:` other than the
  integer 1, booleans or strings where numbers are expected and duplicate
  YAML keys are errors; every problem is collected in `details.errors[]`.

## 7. Decision model

Each applicable rule yields a `RuleResult(rule, outcome, message, details,
waiver_id)` with `outcome` in `pass` | `warn` | `block`:

1. Rules evaluate to `pass`, or to their `action` when violated.
2. `waivers.service.apply_waivers` replaces each violated (`warn` or `block`)
   result covered by a matching waiver with outcome **`warn`**,
   `waiver_id = <id>` and the message prefixed `waived: `.
3. Aggregation: `block` if any result is `block`, else `warn` if any is
   `warn`, else `pass`. A team without a policy gets one result
   `policy.missing` / `warn` and `policy_id = None`.

`Decision.reasons` (stored in `evaluations.reasons` and returned to CI) lists
the non-pass results in policy order:

```json
[{"rule": "dependency.max_severity", "outcome": "block",
  "message": "ledgerkit 2.4.1: MBSA-2026-0141 is critical (max high)",
  "waiver_id": null, "details": {"violations": [{"package": "ledgerkit", "id": "MBSA-2026-0141", "severity": "critical"}]}},
 {"rule": "sast.new_high_max", "outcome": "warn", "message": "waived: 1 new high SAST finding (max 0)",
  "waiver_id": 41, "details": {"new_high": 1, "max": 0}}]
```

## 8. Waivers

Lifecycle: `pending` -> `approved` | `rejected` (security reviewer only);
`approved` -> `revoked` (reviewer, or the owning team) | `expired` (scheduler);
`pending` -> `expired` when `expires_at` passes unreviewed. Other transitions
are 409 `invalid_transition`, and so is reviewing or revoking a waiver whose
`expires_at` has passed but which the scheduler has not swept yet. A
revocation leaves the approval's `reviewed_by` / `reviewed_at` /
`review_note` on the row; who revoked it and why is only in the
`waiver.revoked` audit event. `expires_at` must be in the future and at most
`GATE_WAIVER_MAX_DAYS` (90) days away (422 `waiver_too_long`).

A waiver **matches** a result when: status `approved`, `expires_at > now`,
same team, `service_id` null or equal, `rule` equal (canonical id; a waiver
for `sast.max_high` is stored as `sast.new_high_max`), and `version_range`
null or containing the submission's version (no version -> only waivers
without a range). Several matches: the one expiring last (ties: lowest id).

Version ranges: comma-separated clauses, all must hold, operators `>=`, `>`,
`<=`, `<`, `==`, e.g. `>=4.10.0,<4.13.0`. Versions compare as dot-separated
integers with missing parts as 0 (`4.12` == `4.12.0`); a pre-release suffix
(`4.13.0-rc.1`) sorts before its release.

```python
# gatekeeper/waivers/service.py
def request_waiver(conn, *, team_id: int, service_id: int | None, rule: str,
                   version_range: str | None, reason: str, expires_at: datetime,
                   actor: str) -> dict[str, Any]
def approve(conn, *, waiver_id: int, actor: str, note: str | None = None) -> dict[str, Any]
def reject(conn, *, waiver_id: int, actor: str, note: str) -> dict[str, Any]
def revoke(conn, *, waiver_id: int, actor: str, note: str | None = None) -> dict[str, Any]
def apply_waivers(conn, *, team_id: int, service_id: int, version: str | None,
                  results: list[RuleResult]) -> list[RuleResult]   # reads only
def waiver_view(conn, waiver_id: int) -> dict[str, Any]
def get_row(conn, waiver_id: int, *, lock: bool = False) -> Row     # 404
def list_waivers(conn, *, team_id: int | None, status: str | None = None,
                 service: str | None = None, rule: str | None = None,
                 limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]
# request_waiver also takes max_days: int | None = None (default GATE_WAIVER_MAX_DAYS)
# gatekeeper/waivers/matching.py: canonical_rule, covers, best_match
# gatekeeper/waivers/versions.py: parse_version, parse_range, in_range
# gatekeeper/waivers/expiry.py
def expire_due(conn, *, at: datetime) -> list[int]          # ids moved to expired
# gatekeeper/waivers/notices.py
def send_expiry_notices(conn, *, at: datetime, notice_hour: int | None = None) -> int
    # notices enqueued; notice_hour None = GATE_WAIVER_NOTICE_HOUR
```

`apply_waivers` writes nothing: ingest records `waiver.applied` once the
evaluation row exists, and the dry run calls it too. Waiver view
(`GET /v1/waivers/<id>`, lists, the `waiver` of a `waiver.expiring` callback):

```json
{"id": 16, "team": "payments-api", "service": "payments-api",
 "rule": "dependency.max_severity", "version_range": ">=4.12.0,<4.13.0",
 "reason": "ledgerkit 2.4.1 has no fixed release; upstream patch expected in 2.4.3",
 "requested_by": "key:payments-api-ci", "status": "approved",
 "reviewed_by": "key:security-review", "reviewed_at": "2026-11-23T14:00:00+00:00",
 "review_note": "approved for the 4.12 line only", "expires_at": "2026-12-14T11:00:00+00:00",
 "expiry_notice_sent_at": null, "created_at": "2026-11-23T11:00:00+00:00"}
```

`service` is null for a team-wide waiver; lists are newest first.

Expiry is at the exact `expires_at` instant (since 3.4). Expiry notices: an
approved waiver expiring within 72 hours, not yet noticed, gets one
`waiver.expiring` outbox event to the team's `notify_url` (skipped when null)
during the hour `GATE_WAIVER_NOTICE_HOUR` (09) **in the team's timezone**,
i.e. at the first scheduler run in the first such hour inside the 72-hour
window; `expiry_notice_sent_at` is set to that run's time when enqueued.
Waivers of a team without `notify_url` are not marked, so they get a notice
if one is configured before they expire.

Routes: `POST /v1/waivers` (team key), `GET /v1/waivers?status=&service=&rule=`
(+ `team=` for reviewers), `GET /v1/waivers/<id>`, `POST /v1/waivers/<id>/approve`,
`/reject`, `/revoke`. An unknown `status` filter is 400 `bad_request`; the
`rule` filter accepts the alias.

## 9. Audit

```python
# gatekeeper/audit/service.py
def record(conn, *, action: str, actor: str, subject_type: str, subject_id: int | None,
           team_id: int | None, details: dict[str, Any] | None = None) -> int
```

Written in the caller's transaction. Actions (subject_type in brackets):

| action | written by | details |
|---|---|---|
| `evaluation.decided` [evaluation] | ingest | `decision`, `policy_version`, `rules` (non-pass rule ids), `waiver_ids` |
| `waiver.applied` [waiver] | ingest | `evaluation_id`, `rule` |
| `policy.published` [policy] | evaluation | `version`, `comment` |
| `waiver.requested` / `approved` / `rejected` / `revoked` [waiver] | waivers | `rule`, `service_id`, `expires_at`, `note` |
| `waiver.expired` [waiver] | waivers (scheduler) | `expires_at` |
| `callback.dead` / `callback.replayed` [callback] | callbacks / cli | `event`, `attempts`, `last_error` |
| `team.created` [team], `key.issued` / `key.revoked` [api_key] | cli, seed | `name`, `role` (never the key) |

Actors: `key:<api key name>` for HTTP callers, `scheduler`, `cli:<os user>`,
`seed`. `GET /v1/audit?action=&subject_type=&subject_id=&since=&until=` (+
`team=` for reviewers; team keys see their own team only, reviewers every
team including team-less events), newest first, `since` inclusive and
`until` exclusive. The route reads through

```python
def list_events(conn, *, team_id: int | None, action: str | None = None,
                subject_type: str | None = None, subject_id: int | None = None,
                since: datetime | None = None, until: datetime | None = None,
                limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]
```

## 10. Callbacks and outbox

```python
# gatekeeper/callbacks/service.py
def enqueue(conn, *, team_id: int, event: str, url: str, payload: dict[str, Any],
            evaluation_id: int | None = None) -> int
def replay(conn, *, outbox_id: int, actor: str) -> None   # back to pending, attempts 0, due now
# gatekeeper/callbacks/signing.py
def sign(secret: str, timestamp: int, body: bytes) -> str  # "sha256=<hex>"
def verify(secret: str, timestamp: int, body: bytes, signature: str, *, now: int,
           tolerance_s: int = 300) -> bool
# gatekeeper/callbacks/delivery.py
def backoff_s(attempts: int) -> int                       # min(30 * 2 ** (attempts - 1), 3600)
def deliver_due(*, limit: int = 50) -> int                # opens its own transactions;
                                                          # returns the rows attempted
def url_allowed(url: str, settings: Settings) -> bool
def post(url: str, body: bytes, headers: dict[str, str], timeout_s: int) -> int
    # the only network call: tests replace it (monkeypatch delivery.post)
```

Events: `evaluation.decided` -> `{"event": "evaluation.decided", "evaluation":
<evaluation view>}` to the evaluation's `callback_url`; `waiver.expiring` ->
`{"event": "waiver.expiring", "team": "<slug>", "waiver": <waiver view>}` to
the team's `notify_url`.

Wire format: `POST <url>`, body = the payload as compact JSON (exactly the
bytes signed), headers `Content-Type: application/json`,
`X-Gatekeeper-Event: <event>`, `X-Gatekeeper-Delivery: <outbox id>`,
`X-Gatekeeper-Timestamp: <unix seconds>`, `X-Gatekeeper-Signature:
sha256=<hex HMAC-SHA256(team.callback_secret, "<timestamp>." + body)>`.
Receivers reject timestamps more than 300 s away.

Delivery: rows `pending` with `next_attempt_at <= now` are claimed oldest
first with `FOR UPDATE SKIP LOCKED`, sent with `GATE_CALLBACK_TIMEOUT_S`
(stdlib `urllib`, no redirects). 2xx -> `delivered`. Anything else ->
`attempts + 1`, `last_error`, `next_attempt_at = now + backoff_s(attempts)`;
at `GATE_CALLBACK_MAX_ATTEMPTS` (8) -> `dead` + audit `callback.dead`.
Claiming is a lease: the claim transaction pushes `next_attempt_at` out by
`2 * GATE_CALLBACK_TIMEOUT_S + 60` s and commits, the HTTP call runs with no
transaction or row lock, then one transaction per row settles it. Outside
`GATE_ENV=prod` only `ci-mock`, `localhost`, `127.0.0.1` and `*.example.test`
are called; any other URL goes straight to `dead` ("url not allowed").

## 11. Scheduler

`python -m gatekeeper.scheduler [--once]`. Holds `pg_try_advisory_lock(4150212)`
(`SCHEDULER_LOCK_ID` in `gatekeeper/scheduler/runner.py`) on a dedicated
connection for the life of the process; a second instance waits as standby and
retries every interval. Every `GATE_SCHEDULER_INTERVAL_S` (30 s) it runs, each
in its own transaction and recorded in `scheduler_runs`:

| job | calls |
|---|---|
| `expire_waivers` | `waivers.expiry.expire_due(conn, at=clock.now())` |
| `send_expiry_notices` | `waivers.notices.send_expiry_notices(conn, at=clock.now())` |
| `deliver_callbacks` | `callbacks.delivery.deliver_due()` |

A failing job is logged (`scheduler.job_failed`), recorded with
`last_status = 'error'` and does not stop the others. `--once` runs every job
once and exits (tests, runbook). `runner.Scheduler(engine=None, jobs=JOBS)`
has `try_acquire()`, `tick()` (False on standby), `run_job(name, job)`,
`release()` and `run_forever(stop, interval_s)`; each job in
`scheduler/jobs.py` returns a count (`expire_waivers`, `send_expiry_notices`,
`deliver_callbacks`). Advisory locks are per database, so a test scheduler on
`gatekeeper_test` never competes with the dev stack's.

## 12. HTTP API conventions and error model

- JSON in and out; `Authorization: Bearer gk_demo_...` on every route except
  `/healthz`. Times are ISO 8601 with offset (`2026-12-02T11:00:00+00:00`);
  query times without an offset are 400 `invalid_datetime`.
- Lists: `?limit=` (1..200, default 50) and `?offset=`, response
  `{"data": [...], "meta": {"total", "limit", "offset"}}` (`core.http.page`).
- Bodies are parsed with marshmallow via `core.http.load_body(schema)`.
- Errors: `{"error": {"code", "message", "details"}}` from
  `gatekeeper.core.errors`:

| status | class | codes in use |
|---|---|---|
| 400 | `BadRequest` | `bad_request`, `invalid_json`, `invalid_pagination`, `invalid_datetime`, `invalid_idempotency_key` |
| 401 | `Unauthorized` | `missing_api_key`, `invalid_api_key` |
| 403 | `Forbidden` | `role_required` |
| 404 | `NotFound` | `not_found` (also for another team's rows) |
| 409 | `Conflict` | `idempotency_conflict`, `invalid_transition` |
| 413 | `PayloadTooLarge` | `payload_too_large` |
| 422 | `ValidationFailed` | `validation_failed` (marshmallow messages in `details`), `unknown_payload_format`, `unknown_service`, `evidence_too_large`, `invalid_policy`, `waiver_too_long` |
| 500 | - | `internal_error` (logged with the request id) |

## 13. Cross-cutting conventions

- **Transactions.** Handlers, scheduler jobs and CLI commands open the unit of
  work with `with transaction() as conn:` (`gatekeeper.core.db`). Service
  functions take `conn` first, never commit, never open their own engine
  connection. `transaction()` nests as a SAVEPOINT. Only
  `callbacks.delivery.deliver_due` opens transactions itself (it must not hold
  locks during HTTP calls).
- **Clock.** `gatekeeper.core.clock.now()` (aware UTC) is the only "now";
  write `created_at` and friends from it. Local times (team timezone) are
  computed with `zoneinfo.ZoneInfo(team.timezone)` at the edge.
  `clock.freeze()` (tests) wins over `GATE_NOW` (dev only, refused with
  `GATE_ENV=prod`), which wins over the wall clock. docker-compose sets
  `GATE_NOW=2026-12-02T11:00:00Z` for `app`, `scheduler` and `ci-mock` so the
  demo stack agrees with the seed; a pinned clock does not move.
- **Team scoping.** `g.principal` is set before every view
  (`core.auth.load_principal`). Lists filter on
  `auth.team_scope(conn, request.args.get("team"))` (a team id, or `None` for
  a reviewer looking at every team); single rows call
  `auth.ensure_team_access(row.team_id, "waiver 12")`. Another team's row is
  404, never 403. Reviewer-only routes use
  `@auth.require_role(auth.ROLE_REVIEWER)`; CI-only routes
  `@auth.require_role(auth.ROLE_TEAM)`.
- **Logging.** `log = get_logger(__name__)`; message = event name
  (`<package>.<event>`, e.g. `waivers.expired`), fields via `extra=`. Never log
  payloads, keys or secrets; `core.logging.redact` is the safety net, not the
  plan. Every request logs one `request.completed` line with `request_id`.
- **Settings.** `get_settings()` outside requests, `core.app.current_settings()`
  inside them (tests can pass their own `Settings` to `create_app`).
- **Keys.** Created only through `core.auth.issue_key` (CLI, seed, tests);
  the plaintext is shown once.

## 14. Test helpers

Fixtures in `tests/conftest.py`:

| fixture | what |
|---|---|
| `engine` (session) | engine on `gatekeeper_test`, schema rebuilt with the real migrations once |
| `conn` | connection in an outer transaction, rolled back after the test; every `transaction()` in the code under test (including requests through `client`) runs on it |
| `client` | Flask test client of a session-wide `app` (`create_app()`) |
| `factory` | `tests.factories.Factory(conn)` |
| `frozen_clock` (autouse) | `core.clock` frozen at `TODAY` = 2026-12-02 11:00 UTC; `.advance(hours=2)` |
| `committed_engine` | for `@pytest.mark.committed` tests that need real commits across connections; truncates every table afterwards |

`tests/factories.py`: `TODAY`, `DEFAULT_POLICY` (the YAML of section 6
without `when` on branches), `PASSING_EVIDENCE` (normalized evidence that
passes it), `auth_header(key)`, and `Factory` with `team()`, `service()`,
`team_of(service)`, `team_key()`, `reviewer_key()`, `policy()`,
`evaluation(evidence_data=...)`, `waiver()`, `audit_event()`, `outbox()`.
Every builder takes column overrides as keyword arguments.

Tests live in `tests/<package>/test_*.py`. Run one package with
`make test PYTEST_ARGS="tests/waivers"`.

## 15. Seeded data contract (`python -m gatekeeper.seed`)

Deterministic for a given `--seed` (default 7): 12 teams, 40 services, about
8,000 evaluations over the 12 weeks before 2026-12-02 11:00 UTC
(`--scale N` multiplies evaluations and audit rows), policy history, waivers
in every status, audit events for every decision and review, outbox rows.
Seeded keys are `gk_demo_` + the first 32 hex characters of
`sha256("mossbank-seed:<key name>")`; team keys are named `<team slug>-ci`,
reviewer keys `security-review` and `grace.adeyemi`. Team callback secrets
are `DEMO-whsec-<slug>-` + 12 hex of `sha256("mossbank-seed-secret:<slug>")`.
Callback URLs point at `http://ci-mock:9100/callbacks/<team>/<service>`,
notify URLs at `http://ci-mock:9100/notify/<team>`.

| id | slug | name | timezone | CI |
|---|---|---|---|---|
| 1 | `payments-api` | Payments API | Europe/London | Forgeline v2 |
| 2 | `ledger-core` | Ledger Core | Europe/London | Forgeline v2 |
| 3 | `card-issuing` | Card Issuing | Europe/Dublin | Forgeline v2 |
| 4 | `settlement-sg` | Settlement Singapore | Asia/Singapore | Forgeline v2 |
| 5 | `fx-rates` | FX Rates | Europe/London | Forgeline v2 |
| 6 | `risk-scoring` | Risk Scoring | Europe/Berlin | Forgeline v2 |
| 7 | `kyc-platform` | KYC Platform | Europe/Lisbon | legacy runner |
| 8 | `treasury-tools` | Treasury Tools | Europe/London | legacy runner |
| 9 | `merchant-portal` | Merchant Portal | America/New_York | Forgeline v2 |
| 10 | `data-pipelines` | Data Pipelines | Europe/Warsaw | legacy runner |
| 11 | `mobile-backend` | Mobile Backend | Europe/London | Forgeline v2 |
| 12 | `platform-infra` | Platform Infra | Europe/London | Forgeline v2 |

The Payments API team's services are `payments-api`, `payments-webhooks` and
`refunds-worker`.
