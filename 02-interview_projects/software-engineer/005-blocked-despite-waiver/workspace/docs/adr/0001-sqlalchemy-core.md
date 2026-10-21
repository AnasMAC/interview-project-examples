# ADR 0001: SQLAlchemy Core, no ORM

- Status: accepted
- Date: 2024-09-16
- Deciders: Grace Adeyemi, Tobias Krüger

## Context

Gatekeeper is small, but every release in the company goes through it, and
the security team has to be able to answer "what did the gate see and why
did it decide this" from the database alone. Most of the work is a handful
of inserts per request (an evaluation, its evidence, an audit event) and
reporting queries over a growing evaluations table. The team knows SQL
well; two of us have been bitten by ORM sessions flushing at surprising
times and by lazy loads hiding N+1 queries in reports.

Options considered: the SQLAlchemy ORM, SQLAlchemy Core, raw psycopg with
SQL strings.

## Decision

Use **SQLAlchemy 2.0 Core** with psycopg 3:

- One `MetaData` with every `Table` in `gatekeeper/core/tables.py`, kept in
  step with the Alembic revisions (a test compares them).
- Queries are explicit `select()` / `insert()` / `update()` expressions.
  Rows come back as `Row` objects; views are built with marshmallow schemas.
- No sessions. A request, scheduler job or CLI command opens one
  transaction with `with transaction() as conn:` and passes `conn` down;
  service functions never commit.
- Raw SQL text only for things Core cannot express well (advisory locks,
  `TRUNCATE` in tests and the seed).

## Consequences

- What runs is what you read: no implicit flushes, no lazy loading. A
  report that needs a join says so.
- Slightly more code for simple CRUD than an ORM would need; we accept it.
- Postgres-specific features (JSONB, partial indexes, `FOR UPDATE SKIP
  LOCKED`) are used directly; we do not aim to run on another database.
- Tests run against a real Postgres (`gatekeeper_test`), never SQLite.
