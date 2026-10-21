# Runbook

Owner: Olivia Chen. Day-to-day operations of a local or staging Atlas. All
commands run from the repository root; everything happens in Docker.

## Start, stop, reset

| Task | Command |
|---|---|
| First start on a fresh volume | `make setup` (build, migrate, seed, demo user, up) |
| Start / stop | `make up` / `make down` |
| Start over | `make clean && make setup` |
| Reload demo data, keep the volume | `make seed SEED_ARGS="--reset"` |
| Another host port | `ATLAS_PORT=8100 make up` |
| Second copy of the stack | `COMPOSE_PROJECT_NAME=atlas-b make setup`, then `docker compose -p atlas-b --profile tests down -v` |

`make setup` on a volume that already has orgs stops at the seed step
("Orgs already exist"); that is deliberate. `--reset` truncates every org and
everything that hangs off it, then restarts the id sequences, so the same
`--seed` gives the same ids. Dashboard users survive a reset: their
memberships are re-created for the new orgs.

## Demo data

`python manage.py seed [--seed 42] [--scale N] [--reset]` writes three orgs
(`harborview-bank`, `quillstone-media`, `orchid-grid`) with their demo API
keys and webhook secrets (`docs/architecture.md` §9), and eight weeks of
simulated nightly imports ending at **2026-11-05 14:30 UTC**.

| `--scale` | Harborview | Quillstone | Orchid | Changes | Time |
|---|---|---|---|---|---|
| 1 | ~1,450 | ~2,900 | ~800 | ~28k | ~7 s |
| 8 | ~11,700 | ~40,300 | ~6,400 | ~230k | ~60 s |

Use `--scale 8` for performance work: it is the size Quillstone reported in
REQ-0219. The seed writes rows directly; it does not run the importers or
the merge, so it never sends webhooks. It does run the real ownership and
exposure rules once at the end (`rule_fixes` in its output), so what you see
is what the code computes.

**Dev clock.** The compose stack starts its clock at the seed's anchor
(`ATLAS_NOW=2026-11-05T14:30:00Z` in `docker-compose.yml`): each process
reads that instant on its first `clock.now()` and runs forward in real time,
so expiring certificates and "changed in the last 24 h" match the demo data.
Restarting a service restarts its clock at the anchor, so after a long
session `make down && make up` keeps web and worker together.
`ATLAS_NOW= make up` gives the real clock. Tests freeze the clock themselves
(`tests/conftest.py`) and ignore it.

`python manage.py create_demo_user` (re)creates `demo` / `DEMO-atlas-demo`
with an editor membership in every org. It is safe to run any time.

## API keys

```sh
make shell
>>> from atlas.core.models import Org
>>> from atlas.core.auth import issue_api_key, revoke_api_key
>>> key, raw = issue_api_key(Org.objects.get(slug="orchid-grid"), "cmdb-sync")
>>> raw   # give this to the customer once; only the hash is stored
```

Revoke with `revoke_api_key(key)`. `last_used_at` is updated at most once a
minute per key, so it is approximate.

## Imports and the worker

```sh
docker compose run --rm web python manage.py enqueue_import \
    --org harborview-bank --importer nimbus --path nimbus/harborview-bank-2026-10-28.v2.json
make logs SERVICE=worker
```

Paths are relative to `ATLAS_IMPORT_ROOT` (`fixtures/imports/` locally).
Jobs live in the `jobs_job` table:

| Status | Meaning | What to do |
|---|---|---|
| `queued` | waiting for a worker | nothing |
| `running` | claimed (`locked_by`, `locked_at`) | check the worker logs if it stays here |
| `failed` | will retry at `run_after` (10 s doubling, at most 10 min) | read `last_error` |
| `dead` | permanent error or out of attempts (5) | fix the input, enqueue a new job |

Several workers can run at once (`docker compose up -d --scale worker=2`);
jobs are claimed with `FOR UPDATE SKIP LOCKED`. An import is one
transaction: if it fails, nothing of it is kept. Nothing reclaims a job
whose worker died mid-run: it stays `running` with its `locked_by`. Check
that the worker is gone, then re-queue it by hand:

```sql
UPDATE jobs_job SET status = 'queued', locked_by = '', run_after = now() WHERE id = 4711;
```

## Webhooks

Deliveries are rows in `notify_outboxevent`. Locally they go to `mockhook`,
which appends each request to `var/mockhook/deliveries.jsonl` and serves the
last 50 at `GET http://mockhook:9000/hooks` (compose network only). With
`MOCKHOOK_SECRET=<one org's webhook secret> make up` it also checks
signatures, so only that org's deliveries pass (the others get 401 and
retry):

```sh
docker compose exec worker python -c \
  "import urllib.request; print(urllib.request.urlopen('http://mockhook:9000/hooks').read().decode())"
```

Failed deliveries retry with backoff (30 s doubling, at most 1 h) and go
`dead` after 8 attempts. A URL outside `ATLAS_WEBHOOK_ALLOWED_HOSTS` goes
`dead` immediately with `last_error = "blocked host"`. To re-send a dead
event after the customer fixed their endpoint, set it back to `pending`:

```sql
UPDATE notify_outboxevent SET status = 'pending', attempts = 0, next_attempt_at = now()
WHERE id = 4711;
```

## Throttling

Counters live in Django's local-memory cache, so the limit (600/min per key)
is per web process. With `runserver` there is one process; with several
gunicorn workers a client can get N times the limit. Moving the counters to
a shared cache is on the roadmap; until then do not promise customers an
exact limit.

## Logs

JSON lines (`ATLAS_LOG_FORMAT=json`) with an event name as the message
(`import.completed`, `webhook.failed`) and details as fields. API keys and
webhook secrets are masked by the formatter as a last line of defence; do
not rely on it, never log headers or request bodies.

## Benchmarks

```sh
make seed SEED_ARGS="--reset --scale 8"
docker compose run --rm web python manage.py create_demo_user
make bench
```

`scripts/bench.py` times the API search (first page, filtered, a cursor 50
pages deep), the dashboard list and the CSV download for each org through
Django's test client, and prints median and worst milliseconds and query
counts. It needs no published port. Compare numbers on the same machine only.

## Database

`make psql` opens psql on the dev database; `make shell` opens a Django
shell. Tests use their own database (`test_atlas_test`), never the dev one.
Migrations were squashed at 0.14.0: each app has a single `0001_initial`
dated 2026-09-14, and new migrations start at `0002_`.
