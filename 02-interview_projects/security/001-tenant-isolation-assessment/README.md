# Assess Bellpost for tenant isolation and role security flaws

**Monday 11 May 2026, 09:30 (UTC+01:00).** You are a security engineer at Glasswick, which builds Bellpost, a multi-tenant helpdesk SaaS platform. Glasswick is preparing for the upcoming v1.5 release for Brightpath Labs and Cascade Freight. Iris Malmgren (CTO) and Emre Karaca (security engineer) asked you to assess the platform for cross-tenant isolation and privilege escalation vulnerabilities before the release freeze.

## Your mission

Conduct an initial security assessment of Bellpost focusing on tenant isolation (API and attachments) and role-based access control in the admin console. Deliver a clear, actionable security findings register in `CHOICES.md` with reproducible local proofs of concept demonstrating cross-tenant impact between Brightpath Labs and Cascade Freight.

At minimum, identify and document at least two real cross-tenant or privilege escalation vulnerabilities with local reproduction steps, refute or contextualize any false alarms, and explain recommended remediation in `CHOICES.md`. Anything beyond that is up to you.

There is no single right answer. You choose what you investigate, how you verify findings, and what depth you explore; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Bellpost codebase: a Python 3.12 Flask and SQLAlchemy application with Postgres database, local email ingest, attachment storage, and admin console. Start with `docs/architecture.md` and `docs/security-notes.md`. `README.md` covers running, testing, and seeding. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup` (starts Docker Postgres, runs migrations, seeds demo tenants). Tests: `make test`.

Everything in `workspace/` is fictional and is the only source of truth for this exercise. Outside research is optional and cannot change the facts here.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your notes, PoC scripts or test reproductions (git commits welcome).
- `CHOICES.md` (at most 300 words): what you investigated and why, what vulnerabilities you verified with proof, what you chose not to do or identified as false alarms or out of scope, and one AI output you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

Result 35 (does it identify genuine vulnerabilities with valid proof and actionable guidance for Iris and Emre), accuracy 25 (correct identification of flaws vs false alarms and out-of-scope tools), judgment 20 (sensible prioritization and realistic impact analysis), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
