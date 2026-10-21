# Triage and verify Bellpost automated scanner findings

**Monday 11 May 2026, 09:30 (UTC+01:00).** You are a security engineer at Glasswick, which builds Bellpost, a multi-tenant helpdesk platform. Marcus Vance (Engineering Lead) ran Larkspur SAST 4.2.0 across the codebase before v1.5 release. The automated scan produced 10 findings from critical to low severity. Marcus asked you to triage the scanner output, separate real vulnerabilities from false alarms, build working proof-of-concept reproductions for verified flaws, and deliver remediation advice before release freeze.

## Your mission

Review scanner findings in `reports/sast_scan_report.json` against the Bellpost codebase. Investigate flagged findings to determine whether each is an exploitable flaw, a false positive, or an out-of-scope legacy artifact. For verified vulnerabilities, build reproducible local proofs of concept and document remediation guidance.

At minimum, verify and reproduce the critical vulnerabilities, refute false alarms with technical reasoning, and summarize your triage decisions in `CHOICES.md`. Anything beyond that is up to you.

There is no single right answer. You choose which findings to prioritize, how to construct reproduction proofs, and how to structure your findings summary; explain your choices in `CHOICES.md`.

## What you have

`workspace/` contains the Bellpost application repository:
- `reports/sast_scan_report.json`: Larkspur SAST 4.2.0 report with 10 findings.
- `app/`: Flask core (ticket routes, admin handlers, attachment streaming, legacy helpers).
- `docs/architecture.md` and `docs/security-notes.md`: Architecture context, tenant models, and security rules.
- `tests/`: Existing test suites and security fixtures under `tests/fixtures/scanner_noise/`.

The codebase is larger than anyone could read in an hour; that is intentional. Setup: `make setup`. Tests: `make test`. Everything in `workspace/` is fictional and is the sole source of truth.

## Rules

- You have **60 minutes** from the moment setup succeeds. The session is recorded.
- Use any AI tools, editors, agents or search you like. We expect you to use AI; we look at how you direct it and check its output.
- The engineer on the call can help with setup, audio or time, but not with the task. If something is unclear, make a reasonable assumption and note it in `CHOICES.md`.
- Do not contact real people or systems, publish anything, or use real credentials. Keys in the workspace are nonfunctional `DEMO` values.

## What to send at minute 60

- Your work: the workspace with your notes, proof-of-concept scripts, test reproductions, or code fixes.
- `CHOICES.md` (at most 300 words): what you investigated, how you separated true vulnerabilities from false positives, reproduction methods, and one AI output you corrected or rejected.

Unfinished work is fine; send what you have and say what you would do next.

## How it is assessed

Assessment is weighted across four scoring categories totaling 100%:
- Vulnerability Verification & False Positive Refutation (35%): Accurately confirm genuine vulnerabilities and refute false alarms without accepting automated scanner output uncritically.
- Proof-of-Concept & Reproduction Rigor (25%): Demonstrate concrete, reproducible proofs or test scripts validating the impact of verified vulnerabilities.
- Risk Prioritization & Remediation Guidance (20%): Prioritize risks sensibly and provide Marcus with clear architectural and code-level fixes.
- Technical Communication & Stakeholder Notes (20%): Articulate your rationale, methodology, and AI direction clearly in `CHOICES.md`.

Every approach can reach full marks. We do not score typing speed, tool choice, hours, polish or volume.
