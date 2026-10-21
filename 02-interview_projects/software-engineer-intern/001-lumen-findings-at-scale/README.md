# Make Lumen's findings list and exports work at their size

**Wednesday 14 October 2026, 10:00 (UTC+01:00).** You are a software engineer intern at Tidewright, which runs simulated security checks for customers and tracks the findings. Lumen Retail now has about 200k findings; their dashboard crawls after the first pages and their daily CSV export times out. Hugo Lefèvre (customer success) owes them an answer this week, and Ama Owusu and Tomasz Wrona will review your change before it is merged.

## Your mission

Hugo needs to tell Lumen, with numbers you measured, that paging through their findings and both CSV exports work at their size. The team needs a change it can merge without breaking anyone who uses the API or the exports today.

At minimum, on the 200k-finding seed, deep pages of `GET /v1/findings` and the CSV report export are clearly faster than your own baseline measurement, every existing consumer keeps working, and `CHOICES.md` gives before and after numbers measured on your machine. Anything beyond that is up to you.

There is no single right answer. You choose how you approach the problem, how you structure the change and how deep you go; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Tidewright Orchestrator: a Python 3.12, FastAPI, Postgres and Redis service (API, worker, scheduler, reporting, operator CLI, about 300 tests, docs). Start with `docs/requests/CS-0391-lumen-export-too-slow.md`, Hugo's ticket. `README.md` covers running, testing, seeding and benchmarks; `docs/` holds the API reference, architecture, runbook and other tickets. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup`, then `make seed SEED_ARGS="--reset --findings-scale 34"` (about 20 s; about 200k findings over three tenants, Lumen about 61k). Run both before the clock starts. Tests: `make test`. The benchmark script and tests use an in-process client; you do not need the host port.

Everything in `workspace/` is fictional and is the only source of truth for this exercise. Outside research is optional and cannot change the facts here.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your changes (git commits welcome).
- `CHOICES.md` (at most 250 words): what you built and why, what you chose not to do, how you checked the result, and one AI output you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

Result 35 (does it work and help Hugo), accuracy 25 (correct against the material), judgment 20 (sensible scope and trade-offs), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
