# Answer a security questionnaire and RFP addendum

You are the Solutions Engineer at the fictional vendor Lantern. Fictional prospect Northwind Ledger, an EU payments company, sent a 24-question technical and vendor-security questionnaire, then a short addendum. Your answer library was built from older RFPs and some entries no longer match the product. Prepare an honest, traceable response that the account executive can act on. The scenario dates (questionnaire received **2026-06-08 09:00 UTC**, addendum **2026-06-10 09:00 UTC**) are separate from your assessment deadline.

## Timing and setup

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Effort is visible through follow-through and verification.

Open these local inputs with any spreadsheet or text editor:

- [Lantern product facts](inputs/product.md), authoritative
- [Northwind questionnaire](inputs/questionnaire.csv)
- [Answer library from older RFPs](inputs/answer_library.csv)
- [Response rules, owners and Northwind's evaluation rules](inputs/response_rules.md)
- [Addendum](inputs/addendum.csv), with six new questions and one change to an existing requirement

Baseline skills: application security concepts (SAST versus DAST, authenticated scanning, SBOM, SARIF), common vendor-security topics (SOC 2, ISO 27001, data residency, SSO), CI/CD basics, careful source checking and concise customer writing. Scripting is optional. All companies, people and product facts are fictional; use the fixtures as the authoritative universe. Outside research is optional and cannot affect marks.

## Core task

1. **Answer matrix.** For all 24 questions, give the category from the response rules, an answer of at most 60 words, the P-IDs it relies on, the library entry you reused or corrected (if any) and any owner whose approval is needed.
2. **Gap summary for Noor** (at most 250 words). Count the must requirements by category, list each must that is not met or is conditional, state what Northwind would need to accept, and give a clear recommendation on whether the bid is viable and what Noor should ask Northwind before the due date. Keep product answers separate from hints that are not in writing.
3. **Escalation list.** Each item names the question, owner, what is needed and when, relative to the response due date.
4. **Corrected, reusable answer library.** Mark every library entry as current or corrected, with the reason and P-ID. Supply a runbook plus repeatable checks (spreadsheet formulas, a checklist or an optional script) that another engineer can run on the next questionnaire. At minimum, the checks must confirm that every must has an answer, no answer contradicts `product.md`, no answer reuses an uncorrected stale entry, no roadmap item has a date and every answer is within the word limit.
5. **Apply the addendum.** Use your library and checks to answer AD01–AD06 and re-answer Q05 under AD07. Produce an updated 30-row matrix and an updated gap summary, and show the check results. Keep the baseline and addendum snapshots distinct.
6. **Cover note** to Lina of at most 150 words that accompanies the updated response. Label it **draft; do not send**.

Do not claim a certification Lantern does not hold, promise a date for any capability, commit to contract or pricing terms, or turn an unconfirmed hint into a “Yes”. Do not contact anyone. A useful response lets Noor make a bid decision without rereading every source.

## Submission and acceptance

Submit an archive or repository containing the baseline and addendum answer matrices (CSV or spreadsheet with CSV exports), both gap summaries, the escalation list, the corrected library with runbook and checks, check output for both snapshots, the cover note and a concise `work_log`. Any readable formats are accepted. Include a 3–5 minute recorded walkthrough **or equivalent accessible text** describing one corrected library entry, your bid recommendation and one check.

Acceptance: every question has exactly one category, an answer and evidence; must counts are reproducible from your matrix; stale library claims do not reach any answer; roadmap answers use the approved wording only; contract and NDA items are routed to the right owner; the gap summary separates written facts from hints; the checks can be rerun on a new batch.

Your work log should record prioritization, one obstacle and response, one validation/refinement, limitations and a next step. No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for drafting, extraction, checks and critique; tool choice is not graded. Check its output against `product.md`. Include a short AI-use note naming the tool or offline method and one output you accepted, corrected or rejected with the reason. If you used no AI, say so; do not fabricate an AI failure. Do not submit full prompt histories or personal account access.

Scoring: **usable result 40; accuracy/verification 25; prioritization 20; communication/handoff 15**. Full marks are possible on the core. No marks for sheer volume, hours worked, software choice, AI detection or polished prose. Optional stretch: propose one product-feedback note for Yasmin based on the gaps; not needed for full marks.
