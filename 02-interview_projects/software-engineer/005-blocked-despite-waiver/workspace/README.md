# Gatekeeper

Mossbank's release gate. Every CI pipeline calls Gatekeeper before a deploy:
it posts build evidence (dependencies, secrets scan, SAST summary, test
results, signing), Gatekeeper evaluates the team's policy and answers
**pass**, **warn** or **block** with reasons. Teams can ask for time-limited
waivers, which platform security reviews. Every decision and override is
audited, and pipelines get a signed callback when they ask for one.

Owned by platform security (`#platform-security`, Grace Adeyemi). Current
version: 3.6.1 (see `CHANGELOG.md`).

## Stack

Python 3.12, Flask 3.0 (app factory + blueprints), SQLAlchemy 2.0 Core with
psycopg 3 (no ORM, see `docs/adr/0001-sqlalchemy-core.md`), Alembic,
marshmallow 3, PyYAML for the policy DSL, gunicorn, pytest 8. Everything runs
in Docker Compose: `db` (Postgres 16), `app` (API), `scheduler` (waiver
expiry, expiry notices, callback delivery), `ci-mock` (a local stand-in for
Forgeline CI that logs callbacks to `var/ci-mock/callbacks.jsonl`).

## Getting started

You need Docker with the compose plugin; nothing else on the host.

```sh
make setup        # build, start db, migrate, seed demo data, start everything
curl -s http://127.0.0.1:8090/healthz
make test         # full test suite against a separate gatekeeper_test database
```

The API listens on `127.0.0.1:8090`. If that port is taken, pick another one:

```sh
GATE_PORT=18090 make up
```

Nothing else is published on the host; `db`, `scheduler` and `ci-mock` are
only reachable on the compose network (`make psql` for the database).

To run a second, isolated copy of the stack (another branch, CI), set a
project name; containers, network and volumes are all prefixed with it:

```sh
COMPOSE_PROJECT_NAME=gk-review make test
docker compose -p gk-review --profile tests down -v
```

## Make targets

| Target | What it does |
|---|---|
| `make setup` | build images, start db, migrate, seed, start all services |
| `make up` / `make down` | start / stop all services |
| `make clean` | stop everything and delete the volumes (dev data is lost) |
| `make migrate` | `alembic upgrade head` on the dev database |
| `make seed` | deterministic demo data; `SEED_ARGS="--scale 5"` for volume |
| `make test` | pytest; `PYTEST_ARGS="tests/waivers -k expiry"` to narrow |
| `make lint` | ruff (pinned) |
| `make logs` | follow logs; `SERVICE=scheduler` to filter |
| `make shell` / `make psql` | bash in an app container / psql on the dev db |
| `make bench` | time scorecard queries and the CSV export on seeded data |

## Trying the API

Seeded keys are listed in `docs/runbook.md`. For example, as the Payments API
pipeline:

```sh
KEY=gk_demo_709fff51dcac6661eec4c8205afc7b4c
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:8090/v1/whoami
curl -s -H "Authorization: Bearer $KEY" "http://127.0.0.1:8090/v1/evaluations?limit=5"
```

The full API is in `docs/api.md`; the policy language in `docs/policy-dsl.md`.

## The demo clock

The seeded history ends at **2026-12-02 11:00 UTC**, whatever today's date
is. So that reports, waiver expiry and expiry notices agree with that data,
docker-compose pins the clock of `app`, `scheduler` and `ci-mock` there with
`GATE_NOW=2026-12-02T11:00:00Z` (`gatekeeper/core/clock.py`). A pinned clock
does not move: every new row gets `created_at` 11:00:00, failed callbacks
wait for a later `GATE_NOW` before they are retried, and a report whose
`until` defaults to "now" leaves out rows created at that exact instant (pass
a later `until`). To let time pass, restart with another instant, or use the
wall clock:

```sh
GATE_NOW=2026-12-06T01:00:00Z make up   # 09:00 Singapore: waiver 20 notice
GATE_NOW= make up                        # wall clock
make up                                  # back to 2026-12-02T11:00:00Z
```

`GATE_NOW` is ignored by the tests (they freeze their own clock at the same
instant) and refused when `GATE_ENV=prod`. Log timestamps (`ts`) are always
the wall clock.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | compose `gatekeeper` db | SQLAlchemy URL (`postgresql+psycopg://...`) |
| `GATE_PORT` | `8090` | host port of the API (compose only) |
| `GATE_ENV` | `dev` | `dev`, `test` or `prod` |
| `GATE_LOG_LEVEL` / `GATE_LOG_FORMAT` | `INFO` / `json` | `text` is easier to read in tests |
| `GATE_MAX_PAYLOAD_BYTES` | `1048576` | larger evidence bodies get 413 |
| `GATE_CALLBACK_TIMEOUT_S` | `5` | per callback HTTP request |
| `GATE_CALLBACK_MAX_ATTEMPTS` | `8` | then the outbox row is `dead` |
| `GATE_SCHEDULER_INTERVAL_S` | `30` | scheduler loop period |
| `GATE_WAIVER_MAX_DAYS` | `90` | longest waiver a team may request |
| `GATE_WAIVER_NOTICE_HOUR` | `9` | local hour (team timezone) for expiry notices |
| `GATE_NOW` | `2026-12-02T11:00:00Z` in compose, unset elsewhere | dev only: pins "now" (see "The demo clock"); empty = wall clock |
| `CI_MOCK_SECRET` | empty | ci-mock checks signatures with this secret, or `<team>=<secret>,...` |

## Layout

```
gatekeeper/core/         config, app factory, tables, transactions, auth, errors, logging, clock
gatekeeper/ingest/       POST /v1/evaluations, Forgeline v2 and legacy-runner adapters, idempotency
gatekeeper/evaluation/   policy DSL, compiler, evaluator, policy versions, dry run
gatekeeper/waivers/      waiver requests, review, matching, expiry, notices
gatekeeper/audit/        audit log
gatekeeper/callbacks/    outbox, signing, delivery
gatekeeper/scheduler/    single-runner loop (Postgres advisory lock)
gatekeeper/reporting/    scorecards, CSV export
gatekeeper/cli/          operator commands (python -m gatekeeper.cli --help)
gatekeeper/seed/         demo data
ci_mock/                 local CI callback receiver
migrations/              Alembic revisions
docs/                    architecture, API, policy DSL, runbook, ADRs, requests
```

Start with `docs/architecture.md`: it lists the tables, the functions each
package exposes, the decision model and the conventions (transactions, clock,
team scoping, logging) every change is expected to follow.

## Conventions in one paragraph

Use `with transaction() as conn:` at the edge and pass `conn` down; take the
time from `gatekeeper.core.clock.now()`; raise `gatekeeper.core.errors`
classes instead of building error responses; scope every query by team with
`auth.team_scope` / `auth.ensure_team_access`; log event names with
`get_logger(__name__)` and never log keys or payloads. New tables or columns
need an Alembic revision and the matching change in `gatekeeper/core/tables.py`.
