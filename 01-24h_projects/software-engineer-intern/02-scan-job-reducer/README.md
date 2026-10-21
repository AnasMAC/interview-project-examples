# Scan job retry state machine with a virtual clock

This is one Software Engineer Intern assessment with a **24-hour** window. Your recruiter assigns one exercise, never all five. Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Follow-through and verification matter more than hours or volume.

A fictional local scan scheduler has repeated jobs after failures and accepted late completion events. Implement an event reducer that makes retry and terminal-state behavior explicit. This is a deterministic simulation; it must never launch scans, contact services, or sleep.

All companies, tenants, assets and product behavior here are **fictional assessment facts**. The supplied fixtures are the authoritative universe. Outside research is optional and cannot affect marks. Do not contact real systems, send real messages, publish, or use production credentials.

## Supplied inputs and setup

You need basic Python, JSON, CLI use, tests, and familiarity with state transitions, retry timing, terminal immutability, event validation, and causal audit traces. Python **3.10 or later**, its standard library, and any local editor are sufficient; no packages, accounts, paid tools, web access or company framework are needed.

- [Starter CLI](app.py): argument parsing and safe JSON loading, with the feature deliberately unfinished.
- [Primary fixture](inputs/primary.json): main business cases, including deliberate inconsistencies.
- [Second fixture](inputs/secondary.json): use it to demonstrate the feature is reusable.
- [Malformed input](inputs/malformed-input.txt): deliberately truncated JSON, despite its .txt extension; use for error handling.
- [Starter smoke checks](tests/app_test.py): four infrastructure checks, **not feature acceptance tests**.

From this project directory:

```sh
python3 --version
python3 app.py --help
python3 -m unittest discover -s tests -p '*_test.py' -v
python3 app.py --input inputs/primary.json
```

The initial smoke suite should pass. The last command should print `STARTER: implement reduce_jobs` to stderr, return **3**, and produce no stdout. This is intentional, not a setup failure. The starter neither solves the feature nor provides a completed output. Replace the placeholder behavior and replace its smoke assertion with feature assertions; keep the help/file-error checks. You may restructure code, but preserve documented CLI options and make the README run commands accurate.

## Core task and observable acceptance criteria

Build a usable feature implementing the following contract. Use JSON on stdout for successful runs, readable diagnostics on stderr for fatal errors, and the documented exit codes. Explain any assumptions without silently changing the rules.

- Input has `policy` with positive integer `max_attempts` and nonnegative integer `backoff_seconds`, unique nonempty `job_id` objects in `jobs`, and an `events` array. Booleans are not integers for this contract. Invalid policy or job definitions fail the request with exit 2.
- All jobs begin `queued`, `attempts: 0`, `next_start_at: 0`. Terminal states are `succeeded, failed, cancelled`.
- `start` is valid only from queued or retry_wait at/after next_start_at. It increments attempts and moves to running. `success` is valid only from running and makes succeeded. `fail` is valid only from running: if attempts < max_attempts, make retry_wait and set next_start_at to event time + backoff_seconds; otherwise make failed.
- `cancel` is valid from any nonterminal state and makes cancelled. No event changes a terminal job. For running or terminal states, `next_start_at` is null; it holds the due time for queued/retry_wait only.
- Events require unique nonempty string `event_id`, nonempty string `job_id`, type in start/success/fail/cancel and nonnegative integer `at`. Diagnose malformed events and unknown jobs without losing valid earlier work. Reserve an event ID on its first occurrence even if that event is rejected.
- Process in supplied order. Maintain a global time watermark initially 0; for every event with a valid integer time, reject time below the watermark, otherwise advance the watermark even if another rule rejects the event. Equal timestamps are allowed. Do not reorder events.
- Output `jobs` sorted by job_id with `job_id,state,attempts,next_start_at`; `audit` for every input event with one-based `row,event_id,accepted,reason` and resulting job state when known; and `summary` with accepted_events/rejected_events. A valid stream with rejected events exits 0.
- File/top-level errors exit 2. Empty jobs/events are valid. The reducer is pure: repeating identical input yields identical output.

Primary must finish j1 failed at 2 attempts, j2 succeeded at 1, j3 cancelled at 0, with 7 accepted and 6 rejected events. Test exact retry boundary, early retry, terminal immutability, out-of-order time, unknown jobs, duplicate event IDs, and second-stream success.

Add meaningful automated checks that test results and errors, not just that code runs. Include at least one boundary case you construct, and one failing case you fix or a validation that causes a refinement. A clear, tested core earns full marks. Optional stretch: improve the local developer experience or add a useful extra test; no stretch is necessary. A web service, full framework, database, public deployment, or large architecture is outside the core scope.

After implementing the core, use these exact local verification runs. Initially every valid fixture invocation returns the documented exit-3 placeholder; after implementation, each should succeed and match the criteria above.

```sh
python3 app.py --input inputs/primary.json
python3 app.py --input inputs/secondary.json
```

## Time and AI use

Plan your own time within the 24-hour window. Prioritize the core contract and leave time for verification instead of adding features.

**AI is allowed and encouraged** for coding, explanation, test generation, critique and optional research. Tool choice is not graded. No AI tool is provided; you may use any AI tool you already have, and no purchase is required. Free/offline tools and completing the exercise without AI are supported. Check AI output against the rules, input rows and executed tests. Submit a short AI-use note with one concrete accepted, corrected or rejected output and how you checked it; if you did not use AI, state that. Do not invent an AI failure or share complete prompt histories, private account access, or secrets.

## Submission

Submit an archive or repository containing runnable source, tests, the supplied inputs, and:

1. A short run guide with exact commands for both fixtures and the meaningful checks; include representative outputs or assertions with input row/key references.
2. A concise decision/work log: priorities and what you deferred; one obstacle and response; one validation/refinement; known limits and next step. Cite fixture source IDs, event IDs, finding keys or row numbers as evidence.
3. The AI-use note described above.
4. A 3–5 minute walkthrough recording **or equivalent accessible text** explaining the core workflow, one edge case, and evidence of execution.

You do not need a public repository, deployment, PDF or proprietary tools. Document incomplete behavior honestly. Do not submit only a design or report: the runnable feature and reproducible tests are the primary deliverables.

Published scoring: **usable result 40, accuracy/verification 25, prioritization 20, communication/handoff 15**. Full marks are available on the core alone. Tool choice, AI-detector judgments, prose polish, hours worked and sheer output volume are not scored.
