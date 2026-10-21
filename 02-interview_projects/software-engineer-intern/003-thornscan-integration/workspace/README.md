# Ledger

Ledger is the Fernwick AppSec team's findings ledger. CI jobs upload the
reports of our security scanners (Brackish and Thistle for SAST, Kitewatch
for DAST, Depwarden for dependencies, plus pentest reports as CSV); Ledger
normalizes and deduplicates them across tools and runs, assigns each finding
to the owning team, tracks remediation SLAs and produces the weekly team
reports.

Questions: `#appsec-ledger` or appsec@fernwick.example.test. Architecture and
module contracts: [docs/architecture.md](docs/architecture.md). Operations:
[docs/runbook.md](docs/runbook.md).

## Requirements

Python 3.11 or 3.12. Nothing else: Ledger uses only the standard library and
SQLite. No Docker, no virtualenv needed (one does not hurt).

## Quick start

```sh
make setup      # creates var/ledger.db, applies migrations, loads demo data
make demo       # ingests the sample scanner outputs in samples/
make test       # unit tests
make run-api    # JSON API on http://127.0.0.1:8765
```

`make help` lists every target. `make seed SCALE=17` builds a database of
about 51,000 findings for performance work; `make bench` times the sample
ingest, the weekly report and the CSV export on a throw-away scale-17
database (it never touches `var/`). `make setup` can be re-run at any time:
it reseeds with `--reset`, which drops whatever `make demo` added. A second
`make demo` without it reports every file as already ingested (exit 1). If port
8765 is taken: `make run-api LEDGER_PORT=8800`.

### Without make (Windows)

Run the same commands from the repository root:

```sh
python3 -m ledger migrate
python3 -m ledger seed --reset --scale 1
python3 -m ledger ingest --manifest samples/manifest.json
python3 -m unittest discover -s tests -t .
python3 -m ledger.api
python3 scripts/bench_ingest.py
```

Use `py -3` instead of `python3` if that is how Python is installed. Windows
has no system time zone database: `py -3 -m pip install tzdata` once if you
see "unknown time zone".

## Using it

```sh
python3 -m ledger ingest --repo checkout-api --branch main \
    --commit 4be1f0c9d2 samples/brackish/checkout-api/<file>
python3 -m ledger findings --team payments --severity high --status new --status open --status reopened
python3 -m ledger triage 42 --set accepted_risk --note "compensating WAF rule, see SEC-311"
python3 -m ledger report --week 2026-09-14 --team payments --format md
python3 -m ledger sla-check --team payments
```

Filters are repeatable and OR-ed per flag. `--status` is the literal
lifecycle state: `--status open` alone leaves out `new` and `reopened`
findings, which reports and SLA checks also count as open. `report --week`
takes the Monday the week starts on; `--format csv` exports all findings and
ignores `--week`.

API (tokens in `config/ledger.toml` are DEMO values for local use):

```sh
curl -H "Authorization: Bearer DEMO-ldg-ro-7f3a9c21e5b84d60" \
    "http://127.0.0.1:8765/api/v1/findings?team=payments&severity=critical&limit=20"
```

## Configuration

Settings come from `config/ledger.toml`; environment variables win.

| Variable | Default | Meaning |
|---|---|---|
| `LEDGER_CONFIG` | `config/ledger.toml` | alternative settings file |
| `LEDGER_DB` | `var/ledger.db` | SQLite database path |
| `LEDGER_HOST` / `LEDGER_PORT` | `127.0.0.1` / `8765` | API bind address; change the port if 8765 is taken |
| `LEDGER_LOG_LEVEL` / `LEDGER_LOG_FORMAT` | `INFO` / `text` | `json` for one JSON object per line |
| `LEDGER_TIMEZONE` | `Europe/Berlin` | calendar for SLA business days and report weeks |
| `LEDGER_NOW` | unset | freeze "now", e.g. `2026-09-23T14:00:00+02:00`, for reproducible reports |
| `LEDGER_READ_TOKEN` / `LEDGER_ADMIN_TOKEN` | unset | replace the configured tokens of that role |

SLA days per severity: `config/sla.toml`. Holidays: `config/holidays.toml`.
Team ownership of paths: the `OWNERS` file of each repository
(`samples/repos/<repo>/OWNERS` for the sample repositories).

## Layout

```
ledger/core/        settings, SQLite, migrations runner, clock, logging, errors, models
ledger/migrations/  NNNN_name.sql schema migrations
ledger/parsers/     scanner formats: SARIF, Kitewatch JSON, Depwarden XML, pentest CSV
ledger/normalize/   paths, severities, CWE
ledger/dedupe/      fingerprints, cross-tool merge, baseline, lifecycle, ingest pipeline
ledger/ownership/   OWNERS files and teams
ledger/sla/         SLA policy, business days, breaches
ledger/api/         stdlib HTTP JSON API
ledger/reports/     weekly Markdown/HTML reports, CSV export
ledger/cli.py       command line
ledger/seed.py      deterministic demo data
samples/            scanner outputs and sample repositories used by `make demo`
scripts/            benchmarks
tests/              unittest suites, one directory per package; shared fixtures in tests/helpers.py
docs/               architecture, parser notes, runbook, ADRs, incoming requests
```

## Development

* Run a single package's tests: `make test TESTS=tests/dedupe`, or one module:
  `python3 -m unittest tests.core.test_migrations`.
* Schema changes: add `ledger/migrations/NNNN_short_name.sql` (next free
  number) and run `make migrate`. Never edit a migration that has shipped.
* Use `ledger.core.clock.now()` for the current time, `db.transaction()` for
  writes, and the factories in `tests/helpers.py` in tests.
* `ruff check ledger tests scripts` if you have ruff; it is not required.
