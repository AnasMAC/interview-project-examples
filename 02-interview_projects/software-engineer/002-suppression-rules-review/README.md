# Can the suppression-rules branch ship?

**Wednesday 14 October 2026, 10:00 +01:00.** You are a software engineer at Tidewright, which runs security scans for customers and turns the results into findings. Tomasz opened PR-0217, a "finding suppression rules" feature (REQ-0150) drafted mostly by an AI assistant, and he is on a customer call for the next two days. Northpeak Health has built its integration against the API in that PR and is waiting. Nadia Petrov, the product manager, has to tell them today whether it ships.

## Your mission

Give Nadia a decision she can act on today: merge, merge with fixes, or not yet, backed by evidence.

At minimum, apply the branch, back every blocking issue you report with a failing test or an exact reproduction, and deliver either a fixed branch whose tests pass or a clear "not yet" with the smallest list of changes it needs. An evidence-backed "not yet" is a complete answer. Anything beyond that is up to you.

There is no single right answer. You choose how deep to go, which problems to fix and how; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Tidewright Orchestrator code base (Python 3.12, FastAPI, Postgres, Redis, Docker Compose) with its tests and docs. The pull request is in `docs/pr/`: the description, the review thread and the patch itself, not yet applied. The request is `docs/requests/REQ-0150-suppression-rules.md`; `docs/architecture.md` and `docs/api.md` describe how the system behaves today. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup` (run it before the clock starts). Then apply the branch: `git apply docs/pr/PR-0217-suppression-rules.patch`, `make migrate`, then `docker compose restart worker scheduler` (they do not reload code). Tests: `make test`.

Everything in `workspace/` is fictional and is the only source of truth for this exercise. Outside research is optional and cannot change the facts here.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your changes (git commits welcome), including your review or decision for Nadia in any form you like.
- `CHOICES.md` (at most 250 words): what you built and why, what you chose not to do, how you checked the result, and one AI output you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

Result 35 (does it work and help Nadia decide), accuracy 25 (correct against the material), judgment 20 (sensible scope and trade-offs), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
