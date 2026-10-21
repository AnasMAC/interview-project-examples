# Gatekeeper HTTP API

Base URL locally: `http://127.0.0.1:8090` (`GATE_PORT`). In production:
`https://gatekeeper.mossbank.example.test`. Contracts behind these routes
(tables, decision model, callback signature) are in `docs/architecture.md`.

## Conventions

- Every route except `/healthz` needs `Authorization: Bearer gk_demo_...`.
  A **team key** sees and changes only its own team; another team's row is
  `404`, never `403`. A **security reviewer** key sees every team and passes
  `?team=<slug>` to narrow a list.
- JSON in and out. Times are ISO 8601 with an offset
  (`2026-12-02T11:00:00+00:00`); a query time without one is `400
  invalid_datetime`.
- Lists take `?limit=` (1 to 200, default 50) and `?offset=` and answer
  `{"data": [...], "meta": {"total", "limit", "offset"}}`.
- Errors are `{"error": {"code", "message", "details"}}`. Pipelines branch
  on `code`, so codes are part of the contract:

| status | codes |
|---|---|
| 400 | `bad_request`, `invalid_json`, `invalid_pagination`, `invalid_datetime`, `invalid_idempotency_key` |
| 401 | `missing_api_key`, `invalid_api_key` |
| 403 | `role_required` |
| 404 | `not_found` |
| 409 | `idempotency_conflict`, `invalid_transition` |
| 413 | `payload_too_large` (body over 1 MiB) |
| 422 | `validation_failed`, `unknown_payload_format`, `unknown_service`, `evidence_too_large`, `invalid_policy`, `waiver_too_long` |

Every response carries `X-Request-Id` (yours if you sent a valid one).
Quote it when you report a problem.

## Health and identity

`GET /healthz` (no key): `{"status": "ok", "version": "3.6.1"}`, or 503
`degraded` when the database is unreachable.

`GET /v1/whoami`: `{"key": "payments-api-ci", "role": "team", "team": "payments-api"}`.

## Evaluations

`POST /v1/evaluations` (team keys only). The body is the CI payload as is:
Forgeline v2 (`"schema": "forgeline/v2"`) or the legacy runner
(`"runner": "legacy-runner/1.x"`); see architecture.md section 5 for both
formats. The service must exist in your team (`422 unknown_service`).

Send `Idempotency-Key: <1-128 chars of [A-Za-z0-9._:-]>` and retry freely:
the same key with the same payload answers `200` with the stored decision and
`Idempotent-Replay: true`; the same key with a different payload is `409
idempotency_conflict` (`details.evaluation_id`).

`201` response:

```json
{"id": 7922, "team": "payments-api", "service": "payments-api", "source": "forgeline_v2",
 "pipeline_id": "fl-77922", "commit_sha": "3b0d...", "branch": "main",
 "environment": "production", "version": "4.12.3", "decision": "warn",
 "reasons": [{"rule": "dependency.max_severity", "outcome": "warn",
              "message": "waived: ledgerkit 2.4.1: MBSA-2026-0141 is critical (max high)",
              "waiver_id": 16, "details": {"violations": [...], "count": 1, "max": "high"}}],
 "policy_version": 4, "created_at": "2026-12-01T16:38:16+00:00"}
```

`reasons` lists every result that is not a plain pass, in policy order. CI
should fail the job on `block` only; `warn` is for humans. `created_at` is
UTC with whole seconds.

Validation, in the order a pipeline meets it: a body over 1 MiB is `413`;
anything but a JSON object is `400 invalid_json`; a payload that is neither
Forgeline v2 nor legacy runner is `422 unknown_payload_format`; any string
longer than 512 characters anywhere in it is `422 evidence_too_large`
(`details.path`), as are more than 5,000 packages, 200 vulnerabilities on one
package or 1,000 secret findings; schema errors are `422 validation_failed`
with the field messages in `details`. Forgeline `git.ref` must be
`refs/heads/...`, `refs/tags/...` or a bare branch name (`refs/pull/...` is
`422`). Legacy vulns without an `ecosystem` are stored as `"unknown"`.

Every new evaluation that names a callback URL is sent back once, even if two
pipelines post the same commit; an idempotent replay sends nothing.

`GET /v1/evaluations/<id>`; `GET /v1/evaluations?service=&decision=&branch=`
(newest first; reviewers add `team=`; a `decision` other than `pass`, `warn`
or `block` is `400 bad_request`).

## Policies

| route | who | what |
|---|---|---|
| `GET /v1/policies` | team, reviewer (`?team=` optional) | versions, newest first |
| `GET /v1/policies/<version>` | team, reviewer (`?team=` required) | one version with its YAML |
| `POST /v1/policies` | same | `{"source": "<yaml>", "comment": "..."}` publishes the next version, `201` |
| `POST /v1/policies/dry-run` | same | evaluate sample evidence, store nothing |

Dry-run body: `service`, `branch`, `environment`, `version` (nullable),
`evidence` (normalized, as in architecture.md section 5) and optionally
`source` to try a draft instead of the active policy. The answer has
`decision`, `policy_version`, `draft`, `reasons` and every `results` entry
(including passes). Approved waivers apply, as in a real evaluation.

The publish response is the stored version (`id`, `team`, `version`,
`active`, `comment`, `created_by`, `created_at`, `source`) plus `warnings`,
e.g. `["rules[2]: sast.max_high is deprecated, use sast.new_high_max"]`. Lists
leave `source` out. A security reviewer must pass `?team=<slug>` to publish,
read one version or dry-run (`400` otherwise).

## Waivers

`POST /v1/waivers` (team keys):

```json
{"service": "payments-api", "rule": "dependency.max_severity",
 "version_range": ">=4.12.0,<4.13.0", "expires_at": "2026-12-14T11:00:00+00:00",
 "reason": "ledgerkit 2.4.1 has no fixed release; upstream patch expected in 2.4.3"}
```

`service` omitted means every service of the team; `version_range` omitted
means every version. `expires_at` must be in the future and at most 90 days
away (`422 waiver_too_long`). The waiver starts `pending`.

| route | who | transition |
|---|---|---|
| `POST /v1/waivers/<id>/approve` | reviewer | pending -> approved (`{"note"}` optional) |
| `POST /v1/waivers/<id>/reject` | reviewer | pending -> rejected (`{"note"}` required) |
| `POST /v1/waivers/<id>/revoke` | reviewer or the owning team | approved -> revoked |

Anything else is `409 invalid_transition`, including a review or revoke after
`expires_at` has passed. The scheduler moves waivers to `expired` when
`expires_at` passes, and sends one `waiver.expiring` notice to the team's
notify URL during the 09:00 hour (team time zone) in the last 72 hours; a
team without a notify URL gets none. Lists:
`GET /v1/waivers?status=&service=&rule=` (newest first; reviewers add
`team=`; an unknown `status` is `400 bad_request`), single rows at
`GET /v1/waivers/<id>`. A waiver as every route returns it:

```json
{"id": 16, "team": "payments-api", "service": "payments-api",
 "rule": "dependency.max_severity", "version_range": ">=4.12.0,<4.13.0",
 "reason": "ledgerkit 2.4.1 has no fixed release; upstream patch expected in 2.4.3",
 "requested_by": "key:payments-api-ci", "status": "approved",
 "reviewed_by": "key:security-review", "reviewed_at": "2026-11-23T14:00:00+00:00",
 "review_note": "approved for the 4.12 line only", "expires_at": "2026-12-14T11:00:00+00:00",
 "expiry_notice_sent_at": null, "created_at": "2026-11-23T11:00:00+00:00"}
```

`service` is `null` for a team-wide waiver. A revoked waiver keeps the
approving reviewer in `reviewed_by`; who revoked it is in the audit log.

## Audit

`GET /v1/audit?action=&subject_type=&subject_id=&since=&until=`, newest
first (`since` inclusive, `until` exclusive). Team keys see their own team's
events; reviewers see every team, including events without one, and can
narrow with `team=`. Each event is `{"id", "team", "actor", "action",
"subject_type", "subject_id", "details", "created_at"}`. Actors are
`key:<name>`, `scheduler`, `cli:<user>` or `seed`. Example: everything that happened to
waiver 16:

```sh
curl -s -H "Authorization: Bearer $KEY" \
  "http://127.0.0.1:8090/v1/audit?subject_type=waiver&subject_id=16"
```

## Reports

Both routes take `?days=` (1 to 366, default 28) for a window
`[until - days, until)` ending at `?until=` (default now), and `?team=` for
reviewers. Team keys always get their own team.

`GET /v1/reports/scorecard`:

```json
{"window": {"since": "2026-11-04T11:00:00+00:00", "until": "2026-12-02T11:00:00+00:00", "days": 28},
 "generated_at": "2026-12-02T11:00:00+00:00",
 "teams": [{"team": "payments-api", "name": "Payments API", "timezone": "Europe/London",
            "evaluations": 483, "decisions": {"pass": 327, "warn": 67, "block": 89},
            "block_rate": 0.1843, "warn_rate": 0.1387,
            "waivers": {"requested_in_window": 2, "active": 1, "pending": 0,
                        "expiring_within_7_days": 0, "median_active_age_days": 9.0,
                        "oldest_active_age_days": 9.0},
            "top_failing_rules": [{"rule": "dependency.max_severity", "count": 63,
                                   "block": 36, "warn": 27, "waived": 27}, ...]}]}
```

Waiver figures describe the waivers as they stand at `until`; the rest
covers evaluations created in the window. `top_failing_rules` has at most 5
entries, most frequent first.

`GET /v1/reports/export.csv`: one row per evaluation in the window, oldest
first, with `?service=` and `?decision=` filters. Columns: `id, created_at,
team, service, source, pipeline_id, commit_sha, branch, environment, version,
decision, policy_version, rules, waiver_ids` (`rules` and `waiver_ids` are
`;`-separated). Cells that a spreadsheet would run as a formula are prefixed
with `'`.

## Callbacks

When the payload names a callback URL, the decision is POSTed there as
`{"event": "evaluation.decided", "evaluation": {...}}` with
`X-Gatekeeper-Event`, `X-Gatekeeper-Delivery`, `X-Gatekeeper-Timestamp` and
`X-Gatekeeper-Signature: sha256=<hex>`, an HMAC-SHA256 with your team's
callback secret over `"<timestamp>." + body`. Reject timestamps more than
300 s away. Failed deliveries are retried with backoff (30 s doubling, at most
1 h) up to 8 attempts.
