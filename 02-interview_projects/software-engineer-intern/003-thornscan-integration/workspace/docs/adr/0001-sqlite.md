# ADR 0001: One SQLite file, standard library only

- Status: Accepted
- Date: 2025-01-20
- Deciders: Jonas Albrecht, Ewa Kowalczyk, Samuel Okafor

## Context

Until January 2025 scanner results lived in a shared spreadsheet that
Samuel updated by hand every Monday. We want a tool that CI jobs feed
directly, that keeps history (first seen, fixed, reopened) and that answers
"what does team X have open, and what is overdue".

The expected size is small: about 15 repositories with security scanning,
four or five scanners, a few thousand open findings, and writes only from
CI jobs and the occasional triage call. Six people maintain it next to
their AppSec work. Every dependency is something we have to patch, review
and explain to the platform team's supply-chain policy, which requires a
review for each new third-party package in an internal service.

Options considered:

1. **PostgreSQL** on the platform team's shared cluster, with an ORM.
   Strong concurrency and tooling, but it means a database to request,
   credentials to rotate, a driver dependency, and a local database for
   every developer and every CI test job.
2. **A document store** (JSON files per repository in a Git repository).
   Easy to read, but queries across teams and history become our own code,
   and concurrent CI writes conflict.
3. **SQLite** through `sqlite3` from the standard library, one file on the
   Ledger host.

## Decision

Ledger stores everything in one SQLite database file (`var/ledger.db`
locally, a persistent volume on the shared instance) and uses only the
Python standard library at runtime: `sqlite3`, `http.server`, `argparse`,
`xml.etree`, `csv`, `json`, `tomllib`, `zoneinfo`.

- WAL journal mode, `synchronous=NORMAL`, foreign keys on, busy timeout
  5 s. Readers never block the writer.
- Every write runs in an explicit transaction started with
  `BEGIN IMMEDIATE`, so concurrent ingests queue on the busy timeout
  instead of failing on a lock upgrade.
- Schema changes are plain numbered SQL files applied by our own small
  runner (`ledger/core/migrations.py`). No migration framework.
- Tests create a fresh database file per test case in a temporary directory.

## Consequences

- Setup is `make setup` on any machine with Python 3.11+; tests need no
  services and run in parallel.
- One writer at a time. CI ingests are short (well under a second per file),
  so queueing is fine at our volume. A burst of more than a few seconds of
  writes will hit the busy timeout and fail the ingest; the CI job retries.
- The database must live on local disk. SQLite over network file systems
  corrupts WAL databases; the shared instance uses a local volume and a
  nightly `.backup`.
- No horizontal scaling. If we ever need more than one API process writing,
  we revisit this decision; the repository helpers in `ledger/core/repo.py`
  keep SQL in a few places to make that move possible.
- We write some things a framework would give us (router, migrations,
  validation). They are small and tested.
