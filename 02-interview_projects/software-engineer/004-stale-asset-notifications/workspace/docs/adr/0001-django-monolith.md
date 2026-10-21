# ADR 0001: One Django project, one Postgres, no broker

- Status: Accepted
- Date: 2025-05-21
- Author: Olivia Chen
- Reviewers: Daniel Mensah, Aiko Tanaka

## Context

We are three engineers and need, by the end of June, a first version of
Atlas that a pilot customer (Harborview) can use: a REST API for their
scripts, a dashboard for their security team, and background imports of
zone files and cloud inventories that can take a minute each. Customer data
must be strictly separated per org. Nobody on the team wants to run a broker
or a frontend build pipeline on day one.

Options we looked at:

1. **Django + DRF + server-rendered templates, Postgres as the job queue.**
   One codebase, one database, admin-grade auth and migrations for free.
2. **FastAPI for the API, a React single-page app, Celery with Redis.**
   Nicer API ergonomics; three deployables, two build systems, and a broker
   whose failure modes we would learn in production.
3. **Separate services per concern** (ingest, inventory, notifications).
   Clean boundaries on paper; far too much operational surface for three
   people.

## Decision

Option 1. One Django project with apps per concern (`core`, `assets`,
`jobs`, `exposure`, `notify`, `dashboard`; `importers`, `merge` and `api` as
plain packages). Three processes from the same image: `web`, `worker`
(`manage.py run_worker`, polling a `jobs` table with `SELECT ... FOR UPDATE
SKIP LOCKED`) and, in development only, `mockhook`.

Webhooks go through an outbox table written in the same transaction as the
change that caused them, and the worker delivers them.

The dashboard is Django templates, plain CSS and one small JavaScript file.
Charts are inline SVG rendered on the server.

## Consequences

- An import, its merge, ownership, exposure evaluation and outbox rows commit
  or roll back together. No "asset changed but the webhook was lost".
- Postgres is the only stateful dependency; backups and local setup stay
  simple. Polling costs one cheap query per second per worker.
- Throttle counters use Django's local-memory cache and are therefore per
  process. Acceptable while we run one web process; revisit before scaling
  out.
- The worker is single-threaded per process. Long imports delay webhook
  delivery on that worker; run a second worker if this matters.
- Moving the API to another framework later means re-implementing the
  serializers and auth, but not the domain code, which never imports DRF.
