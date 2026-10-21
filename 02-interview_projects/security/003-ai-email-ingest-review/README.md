# Review and secure the AI-generated email ingestion worker

**Monday 11 May 2026, 09:30 (UTC+01:00).** You are a security engineer at Glasswick, building Bellpost, a multi-tenant helpdesk platform serving Brightpath Labs and Cascade Freight. Priya Patel (Lead Developer) had an AI coding assistant draft the inbound email ingestion pipeline under `app/ingest/` to turn incoming MIME emails into support tickets. Priya plans to merge this branch ahead of the v1.5 release and requested an independent security code review.

## Your mission

Review the AI-generated email ingestion worker in `app/ingest/`. Identify security defects and architectural vulnerabilities introduced by the assistant. Deliver exploit proofs of concept and hardening recommendations in `CHOICES.md`.

At minimum, identify and document at least two critical security vulnerabilities in the ingestion worker with concrete reproduction steps, analyze their multi-tenant business impact, and provide clear code remediation guidance in `CHOICES.md`. Anything beyond that is up to you.

There is no single right answer. You choose how you structure your review, which attack surfaces you prioritize, and how deeply you design structural hardening; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Bellpost codebase: a Python 3.12 Flask and SQLAlchemy application with Postgres database, attachments, and the new email ingestion pipeline in `app/ingest/`. Files under review are `app/ingest/parser.py`, `app/ingest/attachments.py`, `app/ingest/worker.py`, and `app/ingest/receipts.py`.

`docs/architecture.md` outlines the multi-tenant isolation model. The test suite is in `tests/`, and sample incoming emails go in `spool/incoming/`. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup`. Tests: `make test`. Worker: `make worker`.

Everything in `workspace/` is fictional and is the only source of truth for this exercise. Outside research is optional and cannot change the facts here.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your security notes, code patches, or exploit proofs (git commits welcome).
- `CHOICES.md` (at most 300 words): what vulnerabilities you discovered, what you chose to verify or defer, how you evaluated the AI code, and one AI suggestion you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

- AI Code Defect & Vulnerability Identification (35%): finding genuine security flaws in the AI-generated code rather than false positives.
- Exploit Proofs & Security Analysis (25%): demonstrating realistic multi-tenant impact with runnable proofs or execution steps.
- Hardening Architecture & Fix Recommendations (20%): sound engineering guidance to remediate vulnerabilities cleanly.
- Code Review Communication & Developer Feedback (20%): professional, actionable feedback for Priya Patel and clear rationale in `CHOICES.md`.

Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
