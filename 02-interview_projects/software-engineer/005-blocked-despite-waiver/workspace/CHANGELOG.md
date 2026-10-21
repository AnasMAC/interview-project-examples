# Changelog

All notable changes to Gatekeeper. Versions follow semantic versioning;
migrations are named after the release that introduced them.

## 3.6.1 - 2026-12-02

- Waivers: cache waiver candidate lookups to cut evaluation
  latency (GATE-405 follow-up): repeated evaluations no longer query the
  waivers table for every violated result.
- Dev: `GATE_NOW` pins `clock.now()` of the compose stack (default
  `2026-12-02T11:00:00Z`, the demo data's "today"); refused in production.
  ci-mock checks callback timestamps against the same instant.

## 3.6.0 - 2026-10-13

- Logging: callback secrets (`DEMO-whsec-...`) and bearer values are masked
  in every log line, including exception text; previously only API keys
  were.
- `X-Request-Id` from the caller is kept when valid and echoed back.
- `/healthz` reports the version and answers 503 `degraded` when the
  database is unreachable.
- Seed: `--scale` to multiply evaluations for performance work.

## 3.5.0 - 2026-08-04

- Reporting: `GET /v1/reports/scorecard` (block and warn rates, waiver ages,
  top failing rules per team) and `GET /v1/reports/export.csv`.
- CLI: `replay-callback` for dead outbox rows (`--force` for delivered
  ones), `create-service`.
- `make bench`.

## 3.4.1 - 2026-05-26

- Fixed: a waiver approved after its own `expires_at` (late review) was
  briefly listed as `approved`; approval is now refused with 409.

## 3.4.0 - 2026-05-12

- **Waivers expire at the exact `expires_at` instant**, no longer at midnight
  UTC at the end of the expiry date. Matching and the expiry job use the
  same cut-off. Existing waivers keep their stored `expires_at`.
- Waiver lists filter on `rule` and `service`.

## 3.3.0 - 2026-03-17

- Policy `when.environments` accepts `prod`, `stg` and `dev`.
- Legacy runner: severity strings `SEV1`-`SEV4`, `P1`-`P4`, `IMPORTANT`,
  `MINOR` and `NEGLIGIBLE`; unknown strings are treated as `high` and
  logged (`ingest.legacy_unknown_severity`).

## 3.2.0 - 2026-01-20

- **`sast.max_high` renamed to `sast.new_high_max`** to make clear that only
  new findings count. The old id is still accepted as a deprecated alias and
  logs `evaluation.deprecated_rule_alias`; waivers requested for it are
  stored under the new id.

## 3.1.0 - 2025-11-04

- `Idempotency-Key` on `POST /v1/evaluations`: retries return the stored
  decision; a reused key with another payload is 409. Migration `0003`.
- Waivers can be limited to a version range (`>=4.10.0,<4.13.0`).
- `waiver.expiring` notices to the team's `notify_url`, once per waiver,
  during the 09:00 hour team-local time within the 72 hours before expiry.
- Scheduler jobs are recorded in `scheduler_runs`.
- Policy validation reports every problem at once in `details.errors[]`
  with a path.

## 3.0.0 - 2025-09-08

- **Breaking:** one error format for every route,
  `{"error": {"code", "message", "details"}}`; codes are documented in
  `docs/api.md`. The 1.x `{"errors": [...]}` shape is gone.
- **Breaking:** another team's rows answer 404 instead of 403.

## 2.2.0 - 2025-06-30

- `GET /v1/audit` with filters; team keys see their own team.
- Policy dry run: `POST /v1/policies/dry-run`, optionally with a draft.

## 2.1.0 - 2025-04-22

- The scheduler holds a Postgres advisory lock; a second instance waits as
  standby instead of delivering callbacks twice.
- Callback retries back off exponentially (30 s doubling, at most 1 h) and
  stop after 8 attempts (`dead`, audited).

## 2.0.0 - 2025-03-18

- **Waivers**: request, review by the security-reviewer role, expiry
  (ADR 0003), matching during evaluation. A waived violation is reported as
  `warn` with `waiver_id`.
- **Callbacks**: decisions are sent back to CI through an outbox, signed
  with HMAC-SHA256 and a per-team callback secret.
- Migration `0002`: waivers, callback outbox, `teams.callback_secret`
  (backfilled) and `notify_url`, `evaluations.callback_url`.

## 1.2.0 - 2025-01-14

- `tests.min_pass_rate` leaves skipped tests out of the rate.
- Forgeline tag builds (`refs/tags/...`) are evaluated with the tag as the
  branch name instead of being rejected.

## 1.1.0 - 2024-11-25

- Legacy runner payload adapter (`legacy-runner/1.x`) for the teams not yet
  on Forgeline CI.
- Evidence size limits (413 / 422).

## 1.0.0 - 2024-10-07

- First release: `POST /v1/evaluations` for Forgeline CI payload v2, YAML
  policies with versions (ADR 0002), rules `dependency.max_severity`,
  `secrets.allowed`, `sast.max_high`, `tests.min_pass_rate` and
  `signing.required`, rule conditions on branches and environments, audit log,
  API keys with team scoping and the security-reviewer role. Migration
  `0001`.
