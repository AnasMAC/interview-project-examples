# A defensible FenceNote launch

FenceNote is a fictional tool for organizing security findings. Its release handoff mixes approved capabilities, experiments, a small usability study, and enthusiastic draft claims. Prepare a launch that a teammate can safely approve and maintain, including a reusable review workflow tested on a second batch.

## Start and boundaries

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The deadline tests bounded execution, not motivation or sleep sacrifice.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for organizing evidence, drafting, critique, automation, and checks. No purchase is needed. Use free/offline spreadsheets, text, or slides. Tool choice is not graded, and code is not required. Verify AI output against the local inputs; optional external research adds no marks and cannot prove fictional facts. Do not publish, contact anyone, create accounts, use real customer material, or connect systems.

Baseline skills: writing clear copy, comparing statements, organizing a table. No security or legal expertise is needed; supplied terms and policies are sufficient.

## Inputs and setup

Open these files locally; import CSVs with their header rows. Preserve source and claim IDs in your work.

- [Authoritative release sheet and glossary](inputs/release-sheet.md).
- [Evidence packet and review policy](inputs/evidence-and-policy.md), including an older demo note and study limitations.
- [First claim batch](inputs/claims.csv): 10 launch claims to evaluate.
- [Second claim batch](inputs/second-batch.csv): four new requests for testing your workflow.

The release sheet governs released features and availability; the study governs only its measured observations. An older demo note or draft cannot expand those facts. Unknowns may be escalated without an invented answer.

## Core work

1. Create a reusable claim-review system with explicit statuses, source precedence, fields for evidence ID and limitations, decision owner, escalation, approval, and re-review trigger. It can be a spreadsheet/table plus a short rule checklist; it must let a teammate review a new claim consistently.
2. Process all 10 first-batch claims. For each, record status, precise evidence/constraint references, a reason, and approved wording or a justified hold/remove decision. Preserve original wording. Explain at least one reasonable judgment call rather than pretending every claim is binary.
3. Draft one release announcement of at most 250 words and one launch email of at most 150 words, aimed at operations coordinators who already collect findings. Include a clear exercise-only CTA to request a 20-minute synthetic demo, audience/availability boundaries, and no invented price or measurable benefit. Connect every factual statement to reviewed evidence using IDs in comments or an accompanying copy map.
4. Apply your same system to all four second-batch claims without changing its rules merely to fit an answer. Record expected decision, actual result, and any workflow refinement. Rerun one earlier claim to check the refinement or confirm stable correct behavior. Refinement can improve clarity or coverage; do not invent an error if your checks find none. These are manual rule replays or spreadsheet tests, not a requirement to code.
5. Rehearse handoff: show how a draft becomes approved, what blocks distribution, and who rechecks it if evidence changes. Log at least four checks covering unsupported absolutes, numerical claims, feature availability, and CTA expectations. Include actual results and fixes, not only a checklist of intentions.

Keep scope to one release, two copy assets, and one maintainable review workflow. Optional stretch: add an automated text flagger; full marks do not require it or visual design.

## Submission and acceptance

Submit an archive or repository with an opening file, editable review system, completed two batches, two copy assets and evidence map, check/replay log, and handoff instructions. A reviewer must be able to:

- Reapply your rules to a fresh claim and find approver, blockers, and re-review triggers.
- Trace all 14 decisions to supplied evidence, preserving uncertainty where support is absent.
- Find usable release copy whose promises match released functionality and pilot constraints.
- Reproduce the second-batch replay and at least one earlier-claim rerun, seeing expected/actual decisions and a validation/refinement or documented stable result.
- Check four meaningful failure types and understand unresolved items without outside sources.

Include a concise decision/work log: priorities, one obstacle and response, one validation/refinement, limits, and next step. Include an AI-use note with one output accepted, corrected, or rejected and why; no full prompt history, fabricated failure, or account access. Provide a **3–5-minute recording or equivalent concise text walkthrough**, both equally acceptable.

Stop at a reliable core rather than adding channels.

## Scoring

Weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**, total 100. Full marks possible on core alone; no AI detectors, hours-worked, prose-polish, or content-volume score.
