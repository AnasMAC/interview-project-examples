# Bellpost

**Multi-tenant helpdesk for small support teams.** Ticket API, server-rendered
agent console, email ingest, attachments and signed webhooks, in one Python
service over one Postgres database.

Glasswick builds Bellpost; this repository is the product and its local
development stack.

![Bellpost version 1.4.0](https://badges.glasswick.example.test/bellpost/version-1.4.0.svg) ![Python 3.12](https://badges.glasswick.example.test/python-3.12.svg)

## Requirements

* **Python 3.12** (`python3.12` on `PATH`; CI runs 3.12.7). 3.13 is not
  supported yet.
* Docker with Compose v2 (one Postgres container).
* `make` and `curl` (used by `make smoke`).

## Quick start

```sh
cp .env.example .env      # optional; the defaults match this file
make setup                # venv, pinned requirements, db, migrations, demo data
make serve                # http://127.0.0.1:8080/admin
```

`make setup` prints the demo credentials when it finishes. Sign in at
`http://127.0.0.1:8080/admin/login`.

## Commands

| Command | What it does |
| --- | --- |
| `make setup` | Verifies python3.12, creates `.venv`, installs the pinned requirements, starts the database, waits for `pg_isready`, runs `alembic upgrade head` and then `seed/generate.py --seed 1` |
| `make up` / `make down` | Start / stop the database container (data is kept) |
| `make clean` | Stop the database, drop its volume and remove `var/` |
| `make migrate` | `alembic upgrade head` |
| `make seed` | Reload demo data (`SEED_ARGS="--reset"` to wipe existing tenants first) |
| `make serve` | The app on `127.0.0.1:${BELLPOST_WEB_PORT:-8080}` |
| `make worker` | One email-ingest pass over `spool/incoming` |
| `make test` | `pytest -q` against the `bellpost_test` database |
| `make lint` | `ruff check` over `app`, `migrations`, `seed`, `tests`, `tools` |
| `make smoke` | Starts the app briefly and asserts `GET /healthz` returns 200 |
| `make mockhook` | The local webhook receiver |
| `make mock-metadata` | The local instance-metadata stand-in used by the security tests |
| `make psql` / `make logs` | psql on the development database / follow the container log |

`make test` needs the database container: the fixtures create and migrate
`bellpost_test` themselves, but the server has to be up (`make up`).

## Ports and environment

Every published port is overridable; set the values in `.env` (loaded by
`make`) or export them in the shell.

| Variable | Default | What listens there |
| --- | --- | --- |
| `BELLPOST_DB_PORT` | `55432` | Postgres (`docker compose`, host side) |
| `BELLPOST_WEB_PORT` | `8080` | the app and console (`make serve`, `make smoke`) |
| `MOCKHOOK_PORT` | `8900` | the local webhook receiver (`make mockhook`) |
| `MOCK_METADATA_PORT` | `8901` | the local metadata stand-in (`make mock-metadata`) |

Other settings, all optional:

| Variable | Default | Notes |
| --- | --- | --- |
| `BELLPOST_ENV` | `development` | `test` turns on propagation for the suite; `production` secures the session cookie and ignores `BELLPOST_NOW` |
| `BELLPOST_SECRET_KEY` | `DEMO-session-secret-not-for-production` | signs the session cookie |
| `BELLPOST_DATABASE_URL` | `postgresql+psycopg://bellpost:bellpost@127.0.0.1:55432/bellpost` | full SQLAlchemy URL |
| `BELLPOST_ATTACHMENT_ROOT` | `var/attachments` | where uploaded files are stored |
| `BELLPOST_SPOOL_DIR` | `spool/incoming` | where the ingest worker reads mail |
| `BELLPOST_SPOOL_PROCESSED_DIR` | `spool/processed` | processed files, per day |
| `BELLPOST_SPOOL_FAILED_DIR` | `spool/failed` | failures plus an `.error.txt` |
| `BELLPOST_NOW` | unset | freezes the clock for dev and tests; ignored in production |
| `BELLPOST_LOG_LEVEL` | `INFO` | JSON logs on stderr |
| `MOCKHOOK_STRICT`, `MOCKHOOK_SECRET`, `MOCKHOOK_LOG` | `0`, `DEMO-…`, `var/mockhook/deliveries.jsonl` | receiver behaviour |

The `HELPDESK_*` names from the 2019 deployment are still read as a fallback
(`app/config.py`); `config/.env.2019.bak` is the archived file they come from.

## Demo credentials

Everything below is a local demo value, committed on purpose and unusable
anywhere else. `make setup` prints the same list.

| What | Value |
| --- | --- |
| Tenant passwords | `DEMO-<tenant>-<role>`, e.g. `DEMO-brightpath-admin` |
| API tokens | `DEMO-bpk-<prefix>-<role>-0001`, e.g. `DEMO-bpk-brp-agent-0001` |
| Webhook secrets | `DEMO-whsec-brp-0001` (and per webhook) |
| Session secret | `DEMO-session-secret-not-for-production` |
| Metadata stand-in | `DEMO-AKIA-BELLPOST` / `DEMO-not-a-real-secret` |

## The pieces

* **App and console** - `app/`, templates in `app/admin/templates/admin/`.
  `GET /healthz` reports the database connection; it does not look at the
  spool.
* **API** - `app/api/`, documented in `docs/api.md`, including the deprecated
  `GET /api/v1/search` kept for the mobile companion app 3.x line.
* **Email ingest** - `app/ingest/`, reads `spool/incoming/*.eml`, see
  `docs/email-ingest.md`. Run it with `make worker` or
  `python -m app.ingest --spool spool/incoming --once`.
* **Attachments** - `app/attachments/`, files below `var/attachments`; the
  console and the API both enforce the same limits.
* **Webhooks** - `app/webhooks/`, HMAC signed; `make mockhook` is the local
  receiver and `tools/mock_metadata/` is the stand-in the security tests use
  when checking outbound URL rules.
* **Demo data** - `seed/generate.py` (deterministic, `--seed`/`--scale`) plus
  the spool fixtures it writes.

## Tests and lint

```sh
make test                        # 148 tests, needs the db container
make test PYTEST_ARGS="-k ingest"   # one area
make lint                        # ruff, exits 0
make smoke                       # GET /healthz on the running app
```

The suite freezes the clock at `2026-05-11 09:00 +01:00` and starts the two
local mocks on the ports above. Coverage is uneven on purpose in places - see
the test module docstrings for what each file is responsible for.

## Troubleshooting

* **`make setup` says python3.12 is required** - install 3.12 and make sure
  `python3.12` is on `PATH`; `PYTHON=/path/to/python3.12 make setup` works too.
* **Something is already on a port** - set `BELLPOST_DB_PORT`,
  `BELLPOST_WEB_PORT`, `MOCKHOOK_PORT` or `MOCK_METADATA_PORT` in `.env`.
* **`make test` cannot reach Postgres** - run `make up` (or `make setup`)
  first; the fixtures create `bellpost_test` themselves.
* **`make setup` on an existing volume** - the seed refuses to run over
  existing tenants; use `make seed SEED_ARGS="--reset"` or `make clean`.
* **Files pile up in `spool/failed/`** - read the `.error.txt` beside the file;
  nothing is retried automatically (`docs/runbook.md`).
* **A webhook stays `pending`** - the dispatcher runs with the worker; the
  console's webhook page shows the last status code, and retries are capped.

## Documentation

`docs/architecture.md` (decisions), `docs/api.md`, `docs/admin.md`,
`docs/email-ingest.md`, `docs/runbook.md`, `docs/security-notes.md`,
`docs/product/roadmap.md`.
