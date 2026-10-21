# Incident triage from imperfect logs

The fictional HarborDesk helpdesk received a report that Maya's account behaved unusually. You have one exported application log window and the next day's comparison window. Triage the evidence, propose bounded next actions and build a reusable workflow that handles the second window without rewriting its rules.

## Inputs and setup

- [First window: 18 rows](inputs/events.csv).
- [Second window: 8 rows](inputs/second-window.csv).
- [Identity, maintenance and event semantics](inputs/context.md).

All data are synthetic and authoritative. No live system or service exists. Inputs are valid CSV with ISO 8601 timezone-aware timestamps; first-window rows are deliberately unsorted and contain one exact duplicated event. Baseline skills: spreadsheets or basic scripting, sorting/filtering, simple event correlation and cautious security reasoning. Open CSV in a local spreadsheet, or use Python 3.10+ standard library `csv`/`datetime`; no dependency or account required. Retain identifiers when normalizing. Do not send logs anywhere for enrichment.

## Core work and acceptance

1. Create a reusable triage artifact: a script, local spreadsheet with formulas, or explicit rule workflow with a filled decision table. Accept either CSV as input with the same documented rules. It must normalize timestamps, deduplicate exact events, preserve evidence references and produce a chronological timeline, rule matches and prioritized queue. A manual workflow is valid if someone can rerun it using exact steps and rule definitions rather than your judgments alone.
2. Implement the three policy checks in context and show counts and affected evidence IDs. Keep automated rule matches separate from analyst conclusions. Use context to distinguish routine activity from a policy violation. Test at least one quiet/control case and one suspicious case.
3. Apply the same workflow to the second window. Show which findings carry over and which do not; include at least one captured validation of timestamp or duplicate handling. Do not copy first-window conclusions.
4. Write a one-page equivalent incident note: known facts, plausible explanations, unresolved questions, top two next actions and what evidence would change your view. You have authority only to recommend actions; no real accounts to disable and no external contacts.

Acceptance: a reviewer can rerun both windows, reproduce unique-event counts and rule matches, trace conclusions to IDs and distinguish an authorization log from proof of data delivery. Avoid claiming malware, real IP ownership or confirmed exfiltration without evidence. A polished narrative alone is insufficient. Optional stretch: add a visualization of event sequence; not needed for full marks.

## Submission, AI and timing

Submit an archive or repository containing runnable artifacts, source/evidence references, captured verification output and a concise walkthrough (up to five minutes recording **or equivalent accessible text**). Include exact commands and tool versions. Add a short decision/work log recording prioritization, one obstacle and response, one validation/refinement, limits and next step. Add an AI-use note with one accepted, corrected or rejected output and how you checked it; if no AI was used, say so. Never fabricate an AI failure.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for coding, drafting, research, automation and critique. Verify AI output. Tool choice is not graded; free/offline tools are supported, no purchases or personal account access are needed. Synthetic fixtures are the authoritative universe; outside research is optional and cannot affect marks.

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded execution, follow-through and verification, not willingness to sacrifice sleep. Do only this assigned exercise. Full marks are possible on core alone: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**. No AI-detector, writing-volume or prose-polish scoring. Work is an exercise submission, not a company deliverable: no external targets, outreach, production actions or public deployment.
