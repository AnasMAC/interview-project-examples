# Run a week of parallel evaluations and turn feedback into product input

You are the Pre-Sales Engineer at the fictional vendor Lantern. It is **Monday 2026-06-08 08:00 UTC**. You own five prospect evaluations at once and have **16 SE hours** this week. Customers have reported issues in their own words, account executives have typed their own blocker notes, and some tickets are stale. Decide where your week goes, tell the sales manager which deals are at risk, classify every reported issue honestly, and turn the real product gaps into feedback that Product can act on. The scenario dates are separate from your assessment deadline.

## Timing and setup

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is visible through follow-through and verification.

Open these local inputs with any spreadsheet or text editor:

- [Evaluation tracker export](inputs/evaluations.csv)
- [Call notes and success criteria](inputs/call_notes.md)
- [Support and product tickets](inputs/tickets.csv)
- [Release notes](inputs/release_notes.md)
- [Product facts](inputs/product.md)
- [SE desk rules](inputs/capacity_rules.md)
- [SE task backlog with estimates](inputs/se_backlog.csv)
- [Wednesday update](inputs/wednesday_update.md), to apply after your Monday baseline

Baseline skills: working knowledge of application security testing (mobile static and dynamic analysis, authenticated DAST, SARIF and CI exit codes), spreadsheet filtering and date arithmetic, and clear writing for sales and engineering readers. No programming, paid tool, account or outside research is required. All companies, people, product facts, tickets and dates are fictional and authoritative for this exercise. Outside research is optional and cannot affect marks.

## Core task

1. **Evaluation tracker.** For all five evaluations at the Monday snapshot, show urgency, value and risk points, total score, rank, status tier, blocked criteria and evidence IDs. Apply the rules in `capacity_rules.md`; do not trust the `ae_blocker_field` without evidence.
2. **Issue register.** Give each issue I01–I09 exactly one type (bug, missing capability, config or usage, already fixed, duplicate), with the evidence, the canonical issue for any duplicate, the owner and the next action.
3. **Product feedback.** Write the entries the rules require, using the R7 template. Merge duplicates, sum ARR across distinct evaluations, state the workaround and its limit, and promise no date.
4. **Weekly plan and at-risk summary.** Build a plan from the backlog that fits 16 hours, with task, evaluation, owner, deadline and hours, and show the arithmetic. List every deferred task and why. Write an at-risk summary for the sales manager of at most 200 words.
5. **Two technical follow-ups.** Draft one email to Rania (E2) and one to Theo (E5), at most 180 words each, labeled **draft; do not send**. Answer their technical issues and their ServiceNow question accurately.
6. **Reusable desk workflow.** Make the scoring, tiering and planning repeatable: a spreadsheet with formulas, a no-code checklist, or an optional script, plus a short runbook. Apply `wednesday_update.md` to produce a second tracker snapshot and a short replanning note for the rest of the week. Show what changed and one check, such as the hour total or the tie-break order. Keep both snapshots.

Do not contact anyone, open real tickets or promise features, dates, fixes or discounts. Internal pressure to promise a date is not a product fact. Optional stretch: suggest one change to the scoring rules and its tradeoff; this is not needed for full marks.

## Submission and acceptance

Submit an archive or repository containing both tracker snapshots (CSV or spreadsheet with CSV export), the issue register, the product feedback entries, the weekly plan and Wednesday replanning note, the at-risk summary, the two drafts, the reusable workflow with runbook, and a concise work log. Any readable format is accepted. Include a 3–5 minute recorded walkthrough **or equivalent accessible text** explaining one prioritization decision and one check.

Acceptance: every score is reproducible from the rules and cited evidence; every issue has one type and duplicates point to a canonical issue; feedback entries are distinct and their ARR adds up; the weekly plan stays within 16 hours using unchanged estimates; mandatory work is scheduled before optional work; the drafts stay within the product facts and request no credentials. Another engineer must be able to rerun the workflow on the Wednesday update.

Your work log records prioritization, one obstacle and response, one validation/refinement, limitations and a next step. No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for extraction, formulas, drafting and critique; tool choice is not graded. Check its output against the inputs. Include a short AI-use note naming the tool or offline method and one output you accepted, corrected or rejected, with the reason. If you used no AI, say so; do not fabricate an AI failure. Do not submit full prompt histories or personal account access.

Scoring: **usable result 40; accuracy/verification 25; prioritization 20; communication/handoff 15**. Full marks are possible on the core alone. No marks for sheer volume, hours worked, software choice, AI detection or polished prose.
