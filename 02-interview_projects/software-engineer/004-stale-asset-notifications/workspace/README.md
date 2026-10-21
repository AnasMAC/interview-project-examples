# Atlas

Brindlecove's hosted attack-surface inventory. Customers import their
internet-facing assets (DNS zones, Nimbus cloud exports, certificate
transparency feeds, port scans); Atlas merges them into one inventory with
provenance, assigns owners, flags risky exposure and notifies by webhook.

Django 5.1 + Django REST Framework 3.15 on PostgreSQL 16, a Postgres-backed
job queue (`python manage.py run_worker`), server-rendered dashboard. No
Celery, no Redis, no frontend build.

## Quick start

Requirements: Docker with the compose plugin. Nothing else on the host.

```sh
make setup        # build, start db, migrate, seed demo data, create the demo user, start everything
```

Then open <http://127.0.0.1:8000/> and log in as `demo` / `DEMO-atlas-demo`.
The API is under `/api/v1/`:

```sh
curl -H "Authorization: Bearer atl_DEMO_k5lv9z8g76x8az3c8x0ajrk98pwkji8f" \
     "http://127.0.0.1:8000/api/v1/assets/?kind=host&exposure=any"
```

Demo orgs, keys and webhook secrets are in `docs/architecture.md` §9. All of
them are DEMO values for local use only.

Port 8000 taken? Every command honours `ATLAS_PORT`:

```sh
ATLAS_PORT=8100 make up
```

Only the web service publishes a port, and only on 127.0.0.1. `make setup`
is meant for a fresh volume; to start over run `make clean` first, or reload
data with `make seed SEED_ARGS="--reset"`.

The demo data is anchored at 2026-11-05 14:30 UTC, and so is the stack's
clock: compose sets `ATLAS_NOW=2026-11-05T14:30:00Z` (dev settings only), and
each process starts there and runs forward. `ATLAS_NOW= make up` uses the
real clock. `MOCKHOOK_SECRET=<a webhook secret> make up` makes mockhook check
signatures (one secret, so one org). Details in `docs/runbook.md`.

## Make targets

| Target | What it does |
|---|---|
| `make setup` | build, start db, migrate, seed, create demo user, start all services |
| `make up` / `make down` | start / stop the stack |
| `make clean` | stop and delete volumes (dev data is lost) |
| `make migrate` | apply migrations to the dev database |
| `make seed SEED_ARGS="--reset --scale 8"` | deterministic demo data (`--scale` multiplies volume) |
| `make test PYTEST_ARGS="tests/core -k normalize"` | pytest in the `tests` container, on its own database |
| `make lint` | ruff (pinned in `requirements-dev.txt`) |
| `make logs SERVICE=worker` | follow logs |
| `make shell` / `make psql` | Django shell / psql on the dev database |
| `make bench` | time asset search and the dashboard list on seeded data |

Run a second, isolated copy of the stack (CI does this) with a different
project name:

```sh
COMPOSE_PROJECT_NAME=atlas-review make test
docker compose -p atlas-review --profile tests down -v   # when done
```

## Services

| Service | What |
|---|---|
| `db` | postgres:16.4-alpine, compose network only |
| `web` | `manage.py runserver` on `127.0.0.1:${ATLAS_PORT:-8000}`: API, dashboard, `/healthz` |
| `worker` | `manage.py run_worker`: import jobs, exposure evaluation, webhook delivery |
| `mockhook` | local webhook receiver; deliveries land in `var/mockhook/deliveries.jsonl` |
| `tests` | profile `tests`, used by `make test` |

The source is bind-mounted into every container at `/app`, so code changes
apply without a rebuild (the dev server reloads; restart the worker with
`docker compose restart worker`). Rebuild after changing requirements.

## Layout

```
atlas/
  settings/     base, dev, test
  core/         orgs, API keys + DRF auth, clock, normalize, logging, API errors, seed command
  assets/       inventory models, list filters, ownership rules
  api/          REST API (viewsets, serializers, pagination, throttling)
  importers/    zone file, Nimbus v1/v2, CT feed, port scan parsers
  merge/        observations -> assets with provenance
  jobs/         queue, handlers, run_worker
  exposure/     exposure rules
  notify/       change events, webhook outbox, signing, delivery
  dashboard/    views, templates, static
mockhook/       dev webhook receiver
fixtures/       sample import files
scripts/        bench
docs/           architecture, API, runbook, ADRs, requests
tests/          one directory per component; conftest.py + factories.py
```

Start with `docs/architecture.md` (how the parts fit, contracts and
conventions), then `docs/api.md` and `docs/runbook.md`.

## Conventions in one minute

- Time comes from `atlas.core.clock.now()`; tests freeze it at
  2026-11-05 09:30 America/Toronto, the dev stack starts there (`ATLAS_NOW`).
- Every customer-data query starts with `Model.objects.for_org(org)`;
  another org's object is a 404.
- Hostnames, IPs and networks go through `atlas.core.normalize`.
- Never log raw API keys or webhook secrets.
