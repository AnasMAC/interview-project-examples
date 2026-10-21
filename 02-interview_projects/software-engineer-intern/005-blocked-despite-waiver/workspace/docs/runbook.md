# Gatekeeper runbook

Owner: Kwame Boateng (SRE). Escalation: `#platform-security`, then Grace
Adeyemi. Gatekeeper sits in every release path, so when it is down **no
pipeline can release**. Forgeline treats a Gatekeeper timeout as `block`.

## Processes

| service | healthy when | logs |
|---|---|---|
| `app` | `GET /healthz` answers `{"status": "ok"}` | one `request.completed` JSON line per request |
| `scheduler` | `scheduler.lock_acquired` once, then `scheduler.job_finished` every 30 s | `make logs SERVICE=scheduler` |
| `ci-mock` | appends to `var/ci-mock/callbacks.jsonl` | local only |
| `db` | `pg_isready` | |

Application logs are JSON with `request_id`; gunicorn's own start-up lines
are plain text. Keys and callback secrets are masked as `[REDACTED]`; if you
ever see one in clear, treat it as leaked: revoke it and tell security.

Production (`gk-prod-app-1`) runs the same image. `app` is the image's
default command: gunicorn with **2 sync workers** (separate processes) and no
`--reload`; the scheduler runs next to it. A deploy replaces the container
and is logged as `deploy.started` / `deploy.finished`; the log collector
adds `host` and `pid` to every line and wraps gunicorn's plain-text lines
in a `text` field. To restart without a deploy: `gkctl restart app`
(about 10 s, in-flight requests finish first).

## Local demo data

`make setup` seeds the dev database (`python -m gatekeeper.seed`, seed 7):
12 teams, 40 services, about 8,000 evaluations over the 12 weeks before
**2026-12-02 11:00 UTC**, 23 waivers in every status, audit events and
callback outbox rows. The history is anchored at that date, not at the wall
clock, and so is the stack: compose sets `GATE_NOW=2026-12-02T11:00:00Z`, which
pins `clock.now()` of `app`, `scheduler` and `ci-mock` (dev only; see the
README, "The demo clock"). Nothing moves on its own while the clock is pinned:

| to see | run |
|---|---|
| the Singapore team's 09:00 notice for waiver 20 (01:00 UTC) | `GATE_NOW=2026-12-06T01:00:00Z make up` |
| Merchant Portal's 09:00 New York notice for waiver 18 | `GATE_NOW=2026-12-02T14:00:00Z make up` |
| waiver 19 (kyc-platform) expire | `GATE_NOW=2026-12-03T23:00:00Z make up` |
| the wall clock | `GATE_NOW= make up` (seeded waivers then expire by the real date) |

Moving the clock back does not undo an expiry or a sent notice; reseed for a
clean start.

```sh
make seed SEED_ARGS="--reset"              # wipe every table and seed again
make seed SEED_ARGS="--reset --scale 10"   # ~80,000 evaluations, ~25 s
```

The seed refuses to run on a database that already has teams or keys, and
`--reset` is refused when `GATE_ENV=prod`.

### Seeded API keys (demo only)

Keys are `gk_demo_` + the first 32 hex characters of
`sha256("mossbank-seed:<name>")`, so they are the same on every machine.

| key name | role | key |
|---|---|---|
| `payments-api-ci` | team payments-api | `gk_demo_709fff51dcac6661eec4c8205afc7b4c` |
| `ledger-core-ci` | team ledger-core | `gk_demo_9780cd39615df4efa957415315a21870` |
| `card-issuing-ci` | team card-issuing | `gk_demo_d63c7b24907e508f758475fc003ba28c` |
| `settlement-sg-ci` | team settlement-sg | `gk_demo_f2dcce435ff54bf9768e66ee0a4a03b6` |
| `fx-rates-ci` | team fx-rates | `gk_demo_b28054a736fd90391e3c1c0ef08e802d` |
| `risk-scoring-ci` | team risk-scoring | `gk_demo_9c16049699b579b53e1d7a5463081692` |
| `kyc-platform-ci` | team kyc-platform | `gk_demo_afae81c508208e40106f6e5dca45973e` |
| `treasury-tools-ci` | team treasury-tools | `gk_demo_8e873b0ec901b4b0e5a402bad2beb511` |
| `merchant-portal-ci` | team merchant-portal | `gk_demo_b18407593816d234f056760ae8caedb0` |
| `data-pipelines-ci` | team data-pipelines | `gk_demo_0f20fbf10411202fa22fe65cf06766e5` |
| `mobile-backend-ci` | team mobile-backend | `gk_demo_395423bf24e25c21975f9e90553a0f45` |
| `platform-infra-ci` | team platform-infra | `gk_demo_8a74959bdd775269948e3757090930b6` |
| `security-review` | security_reviewer | `gk_demo_3619a3a300d893fb961215d0ba824465` |
| `grace.adeyemi` | security_reviewer | `gk_demo_58f64bee26b143d5e6de4249553d4844` |

Team callback secrets are `DEMO-whsec-<slug>-` + 12 hex characters of
`sha256("mossbank-seed-secret:<slug>")`, e.g.
`DEMO-whsec-payments-api-16b97cb36173`. Database: `gatekeeper` /
`gatekeeper-demo`.

## Operator commands

Run them in an app container (`make shell`). Each is one transaction and is
audited as `cli:<your user>`.

```sh
python -m gatekeeper.cli create-team fx-options --name "FX Options" \
    --timezone Europe/London --notify-url http://ci-mock:9100/notify/fx-options
python -m gatekeeper.cli create-service fx-options options-api
python -m gatekeeper.cli issue-key fx-options-ci --team fx-options   # printed once
python -m gatekeeper.cli issue-key jane.doe --reviewer
python -m gatekeeper.cli revoke-key fx-options-ci
python -m gatekeeper.cli import-policy fx-options policy.yaml --comment "first policy"
python -m gatekeeper.cli replay-callback 6105 6108          # dead rows
python -m gatekeeper.cli replay-callback --force 6110       # also a delivered row
```

The callback secret printed by `create-team` goes into the team's Forgeline
project settings; it is not shown again.

## Scheduler

Only one scheduler runs jobs: it holds Postgres advisory lock `4150212` for
its whole life; others log `scheduler.standby` and retry. Check the jobs:

```sql
SELECT job, last_status, last_finished_at, runs, last_error FROM scheduler_runs;
SELECT pid, datname, application_name FROM pg_locks JOIN pg_stat_activity USING (pid)
 WHERE locktype = 'advisory' AND objid = 4150212;   -- one row per database
```

A `last_finished_at` older than two minutes means no scheduler holds the
lock: restart the service. To run every job once by hand, stop the service
first (`--once` exits 1 when another instance has the lock):

```sh
docker compose stop scheduler
docker compose run --rm scheduler python -m gatekeeper.scheduler --once
docker compose start scheduler
```

## Callbacks

```sql
SELECT status, count(*) FROM callback_outbox GROUP BY 1;
SELECT id, team_id, url, attempts, last_error FROM callback_outbox
 WHERE status = 'dead' ORDER BY id DESC LIMIT 20;
```

A dead row tried 8 times (backoff 30 s doubling, capped at 1 h) and has an
audit `callback.dead`. Fix the receiver first, then replay the rows. A
pipeline that waited on a dead callback can also poll
`GET /v1/evaluations/<id>`.

## Waivers

Expiry is exact: a waiver stops matching at its `expires_at` instant even
before the scheduler marks it `expired`. Expiry notices go out during the
09:00 hour in the **team's** time zone, at most once per waiver
(`waivers.expiry_notice_sent_at`).

## Performance

`make bench` times the scorecard and the CSV export through the Flask test
client on whatever is seeded (`BENCH_ARGS="--json var/bench/latest.json"`
keeps the numbers). Run it before and after a change on the same `--scale`.

## Incidents

1. Note the time, the team and an `X-Request-Id` or evaluation id.
2. `make logs SERVICE=app | grep <request id>`, then the evaluation, its
   audit trail (`GET /v1/audit?subject_type=evaluation&subject_id=<id>`) and
   the team's active policy version.
3. If releases are blocked wrongly and a fix is not minutes away, a reviewer
   approves a short waiver (hours, not days) scoped to the service and rule.
   There is no other override.
