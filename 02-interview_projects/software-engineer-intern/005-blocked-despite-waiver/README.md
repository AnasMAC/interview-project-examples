# Blocked despite the waiver

**Wednesday 2 December 2026, 11:00 +00:00.** You are a software engineer intern in Mossbank's platform-security team, which runs Gatekeeper, the release gate of every CI pipeline. At 10:05 Ben Carter (Payments API) opened GATE-412: the production release of `payments-api` 4.12.3 was blocked although an approved waiver covers it. His next window is 14:00. Grace Adeyemi, the platform-security lead, handed it to you.

## Your mission

Ben and Grace need answers to GATE-412's three asks today (why the same build got a different answer, whether 14:00 can go without a second waiver, which other teams were hit) and a fix the team can deploy.

At minimum, reproduce the root cause with a failing test, make it pass with a fix that keeps waiver behaviour as documented, and answer the three asks in writing; for the third, say how you found the affected decisions and list them from the attached export. Anything beyond that is up to you.

There is no single right answer. You choose how you investigate, how far the fix goes and what form your answers take; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Gatekeeper code base (Python 3.12, Flask, Postgres, Docker Compose) with tests and docs. The ticket is `docs/requests/GATE-412-payments-blocked-despite-waiver.md`; `docs/requests/GATE-412-attachments/` holds this morning's production log, a decisions export and a waivers snapshot. `docs/architecture.md` and `docs/runbook.md` say how it behaves and runs. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup` (run it before the clock starts); the local stack has demo data and a pinned clock (workspace README, "The demo clock"). If port 8090 is busy: `GATE_PORT=18090 make setup`. Tests: `make test`. If you change code while the stack runs: `docker compose restart app scheduler`.

Everything in `workspace/` is fictional and is the only source of truth for this exercise. Outside research is optional and cannot change the facts here.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your changes (git commits welcome), including your answers for Ben and Grace in any form you like.
- `CHOICES.md` (at most 250 words): what you built and why, what you chose not to do, how you checked the result, and one AI output you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

Result 35 (does it work and help Ben and Grace), accuracy 25 (correct against the material), judgment 20 (sensible scope and trade-offs), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
