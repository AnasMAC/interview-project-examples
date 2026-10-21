# Run a proof-of-concept readout against success criteria

You are a Pre-Sales Engineer at the fictional vendor Lantern. The fictional prospect Orchid Pay has finished a 14-day proof of concept (PoC) on two mobile apps and one web portal. The engineer who ran it has moved on, and you now own the readout. Turn the agreed success criteria, the PoC log and two findings exports into an honest, evidence-backed verdict, two audience-specific readouts and a next step. The readout snapshot is **2026-06-15 09:00 UTC**. This is a scenario date, separate from your assessment deadline.

## Timing and setup

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is visible through follow-through and verification.

Open these local inputs with any text editor, spreadsheet or JSON viewer:

- [Agreed success criteria and measurement rules](inputs/success_criteria.md)
- [PoC log, including prospect remarks](inputs/poc_log.md)
- [Round 1 findings export](inputs/scan_findings_round1.json), generated 2026-06-07
- [Round 2 findings export](inputs/scan_findings_round2.json), generated 2026-06-14 after fixes and a rescan
- [Lantern product and engagement facts](inputs/product.md)

Baseline skills: application security concepts (static vs dynamic analysis, authenticated scanning, false positives, common mobile and web issues), reading JSON, CI job results and percentages, and writing for both technical and business readers. Scripting is optional; a spreadsheet works. No Lantern account, scanner, paid tool or network access is needed. All companies, people, apps, hosts and product facts are fictional; the fixtures are the authoritative universe. Outside research is optional and cannot affect marks.

## Core task

1. **Reconciled finding register.** One row per distinct finding across both rounds, with source finding IDs, app, severity, round 1 status, current status and a change class: new in round 2, fixed, newly triaged (open → another non-fixed status), unchanged or not retested. Give row and distinct counts for each export and counts per change class. Do not change any status the exports do not support.
2. **Criteria scorecard.** For C1–C6, give a verdict of met, not met or inconclusive with the evidence IDs (log, scan and finding IDs). Show numerator, denominator and two-decimal results for C4 and C5. For each criterion that is not met or inconclusive, state the cause and what evidence would change the verdict. Also compute C4 and C5 for the **mid-PoC checkpoint** (round 1 export alone).
3. **Technical readout** for Dalia (AppSec Lead), at most 900 words plus tables, labeled **draft; do not send**. Cover results per app, coverage limits, the findings to act on first, and accurate answers to Mehdi's GraphQL question (L16) and Jira remark (L14).
4. **Executive readout** for Karim (CISO and budget owner), at most **250 words**, labeled **draft; do not send**. Give the criteria outcome without hiding misses, what it means for his iOS concern and regulator request (L02), and one recommended next step with owners and dates.
5. **Internal note to Noor**, at most 120 words, answering L18 and stating which parts of your recommended next step need Noor's approval (P8).
6. **Reusable readout workflow.** Provide a spreadsheet with formulas, a no-code checklist or an optional script, plus a runbook another engineer can follow on the next export. It must rebuild the register and compute C4 and C5. Validate it twice: round 1 alone → rounds 1 and 2, and one clearly labeled hypothetical status change of your choice, showing the expected and actual result. Keep the fixtures unchanged.

Do not promise features, dates or extensions that the product facts do not support. Do not state that any app is secure. Do not contact anyone or scan anything; every message is a simulation draft. Optional stretch: a one-slide visual summary of the criteria; it is not needed for full marks.

## Submission and acceptance

Submit an archive or repository containing the finding register (CSV or spreadsheet with CSV export), criteria scorecard, the three drafts, the reusable workflow and runbook with both validation runs, and a concise `work_log`. Any readable formats are accepted. Include a 3–5 minute recorded walkthrough **or equivalent accessible text** explaining one verdict and one check.

Acceptance: a reviewer can trace every verdict and count to fixture IDs; findings are counted by fingerprint, not rows; a finding missing from round 2 is not reported as fixed; the verdict rules are applied as written even when the cause is on the prospect's side; both readouts agree with the scorecard; nothing implies an unsupported capability, a security guarantee or an approved extension; the workflow reruns on a new export without manual reinterpretation.

Your work log should record prioritization, one obstacle and response, one validation/refinement, limitations and a next step. No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for parsing, formulas, drafting and critique; tool choice is not graded. Check its output against the fixtures. Include a short AI-use note naming the tool or offline method and one output you accepted, corrected or rejected with the reason. If you used no AI, say so; do not fabricate an AI failure. Do not submit full prompt histories or personal account access.

Scoring: **usable result 40; accuracy/verification 25; prioritization 20; communication/handoff 15**. Full marks are possible on the core alone. No marks for sheer volume, hours worked, software choice, AI detection or polished prose.
