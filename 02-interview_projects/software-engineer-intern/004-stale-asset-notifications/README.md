# Tell owners when their assets go stale

**Thursday 5 November 2026, 09:30 (UTC-05:00).** You are a software engineer intern at Brindlecove, which runs Atlas, an inventory of customers' internet-facing assets. Harborview Bank and Orchid Grid want to hear about assets no source reports any more. Freya Lindqvist (product) wrote the request and talks to both soon; Daniel Mensah and Rafael Souza will review your change.

## Your mission

Freya needs to tell Harborview and Orchid, truthfully, that Atlas detects stale assets by each org's threshold, notifies their owners once, and shows them in the API and the dashboard, in a change Daniel and Rafael can merge.

At minimum: a per-org threshold (migration); a check run by the worker that sends `asset.stale` through the org's webhooks once per stale period; re-seen assets stop being stale; archived assets never are; an API filter; tests for the exact boundary, a re-seen and an archived asset; and `CHOICES.md` says how you count days and what the first run does. Anything beyond that is up to you.

There is no single right answer. You choose how you model staleness and how far across the layers you go; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains Atlas: Python 3.12, Django 5.1 and DRF on PostgreSQL 16, with a job worker, signed webhooks, a server-rendered dashboard, about 320 tests and docs. Start with `docs/requests/REQ-0214-stale-asset-owner-notifications.md`, comments included. `README.md` and `docs/` cover running, architecture, API and operations. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup` (Docker; builds, seeds three demo orgs and starts the stack; run it before the clock starts). The dev clock (`ATLAS_NOW`) pins the demo to 2026-11-05. If port 8000 is busy: `ATLAS_PORT=8100 make setup`. Tests: `make test`. After code changes while the stack runs: `docker compose restart web worker`, and `make migrate` for new migrations.

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

Result 35 (does it work and help Freya), accuracy 25 (correct against the material), judgment 20 (sensible scope and trade-offs), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
