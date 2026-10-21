# Bring Thornscan's trial results into Ledger

**Wednesday 30 September 2026, 14:00 +02:00.** You are a software engineer intern in Fernwick's AppSec team, which runs Ledger: it collects scanner results from CI, deduplicates them across tools and runs, and tracks them against SLAs. Jonas Albrecht, the AppSec lead, is trialling a new SAST tool, Thornscan, on two Python repositories. The trial ends on 16 October, and today Ledger answers `unknown_format` to every Thornscan report.

## Your mission

Jonas needs to show the teams Thornscan's results inside Ledger, next to Brackish and Thistle, deduplicated, triaged and on SLA, so that he can decide on the tool before the trial ends.

At minimum, both Thornscan reports from 2026-09-22 ingest through `ledger ingest` (format detected from the content, tool `thornscan`), severities are mapped, Thornscan issues merge with other tools' findings where they qualify, suppressed issues do not show up as open work, and an interrupted report is rejected with no writes, with tests; and `CHOICES.md` tells Jonas which of the ticket's expectations hold, which do not, and what he must decide. Beyond that is up to you.

There is no single right answer. You choose how you structure the integration, how far you go beyond the minimum and how you prove it works; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains Ledger (Python 3.11+, standard library only, SQLite; about 6,000 lines and 200 tests). The request is `docs/requests/REQ-0061-integrate-thornscan.md`, including the comments under it. The vendor's format notes and the trial reports are in `samples/thornscan/`; the other tools' sample reports are next to it in `samples/`. `docs/architecture.md` and `docs/parsers.md` describe ingest and deduplication today. It is larger than anyone could read in an hour; that is intentional.

Setup: `make setup` (run it before the clock starts; it needs only Python 3.11+, no Docker). Tests: `make test`. Without make: see the workspace `README.md`.

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

Result 35 (does it work and help Jonas decide), accuracy 25 (correct against the material), judgment 20 (sensible scope and trade-offs), process 20 (how you worked, as seen in the recording). Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
