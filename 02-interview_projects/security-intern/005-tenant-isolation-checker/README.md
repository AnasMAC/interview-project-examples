# Build an automated AST checker for multi-tenant query scoping

**Monday 18 May 2026, 09:30 (UTC+01:00).** You are a security engineering intern at Glasswick, the company behind Bellpost, a multi-tenant helpdesk platform serving enterprise organizations like Brightpath Labs and Cascade Freight. Marcus Vance (Engineering Lead) and the core platform team are preparing for the upcoming quarterly release. In a multi-tenant architecture, data leakage between tenants is a critical vulnerability. While code reviews catch many issues, manual inspection cannot guarantee that every database query enforces tenant isolation.

Marcus Vance has asked you to build an automated AST-based or query-analysis checker that scans Python code for multi-tenant query scoping oversights before code merges into main.

## Your mission

Design and implement an automated checker that inspects Python source files for database queries against multi-tenant models (such as `Ticket`, `Attachment`, or `User`) and verifies that each query is properly scoped by tenant context.

At minimum, your checker must detect real unscoped query vulnerabilities in the application routes, handle legitimate background worker exemptions without noisy false alarms, and provide clear CLI output suitable for automated CI pipelines. Document your design trade-offs, detection approach, and false-positive mitigation strategy in `CHOICES.md`.

There is no single right answer. You choose how you structure the AST traversal, what query patterns you detect, how exemptions are configured, and whether you integrate custom rules; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the full Bellpost source tree:
- `app/api/` and `app/admin/`: Request handlers where every tenant data query must enforce tenant scoping.
- `app/webhooks/` and `app/ingest/`: Background workers and ingest pipelines that process asynchronous jobs across tenants.
- `tools/checkers/tenant_isolation_checker.py`: A starter template providing basic AST traversal and CLI argument parsing. You can expand, refactor, or replace it.
- `docs/architecture.md`: System architecture overview describing tenant boundaries and model relationships.

Setup: `make setup` (sets up database and dependencies). Tests: `make test`. Everything in `workspace/` is fictional and self-contained.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, linters or reference docs you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact external systems, publish artifacts, or use real credentials.

## What to send at minute 60

- Your working checker implementation in `workspace/` (git commits welcome).
- `CHOICES.md` (at most 300 words): your AST detection strategy, how you handled exemptions and false alarms, limitations of static analysis, and one AI suggestion you corrected or rejected.

Unfinished work is fine; send what you have and explain your next steps.

## How it is assessed

Assessment is divided into four categories:
- AST Checker Precision & Bug Detection (35%): Accurately detects unscoped queries on tenant models across API and admin endpoints.
- Exemption & False Positive Handling (25%): Avoids flagging legitimate system workers and cross-tenant deduplication logic.
- CI Integration & Usability Design (20%): Clean CLI ergonomics, meaningful exit codes, and actionable diagnostic messages.
- Technical Documentation & Benchmark Notes (20%): Clear rationale in `CHOICES.md` explaining architectural decisions and static analysis trade-offs.
