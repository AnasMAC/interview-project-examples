# A conversion journey for SignalDesk

SignalDesk is a fictional security-work triage tool. Its pilot team wants small SaaS operations leads to request a guided demo. Your job is to turn supplied audience evidence into a coherent, testable conversion journey that another teammate can operate. The requested artifact is your exercise submission, not a company campaign.

## Start, access, and scope

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded delivery, not willingness to sacrifice sleep.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for drafting, critique, prototypes, rule design, and checking. Do not purchase anything. A local text editor, spreadsheet, slides, or free offline tools are sufficient. Tool choice and code are not graded. Check AI output against the supplied evidence. Outside research is optional, adds no marks, and cannot establish fictional product facts. Do not send messages, use real addresses, run ads, open accounts, publish, or connect forms to a service.

Baseline skills: clear writing, reading a small CSV, basic percentages, and using slides or a spreadsheet. No security expertise or programming is required. Read the glossary before working.

## Supplied inputs and setup

Keep the input files with your work. Open the Markdown files in any editor and import the CSV with a header row. Treat source IDs as references in your output.

- [Product facts and glossary](inputs/product-and-glossary.md): the authoritative capability and terminology boundaries.
- [Audience observations](inputs/audience.csv): six synthetic interview observations, including conflicting requests.
- [Draft campaign and journey constraints](inputs/campaign-constraints.md): a flawed draft, routing rules, baseline, and accessibility requirements.

The synthetic universe above is complete. Where a fact is absent, mark it unknown or make an explicitly labeled design assumption, without inventing a product promise.

## Core work

1. Choose a primary audience and one conversion goal. Briefly justify the choice using at least two audience IDs and explain one audience/request you deprioritized.
2. Build one landing experience plus its conversion path. Include a headline, short explanation, evidence-backed benefit, clear CTA, field labels and privacy copy. Cover these states: initial page; incomplete/invalid form; eligible request confirmation; ineligible request with helpful next step; capacity reached; a keyboard/text alternative. Route fictional examples only. Show what happens after the CTA, who owns the next step, and the promised timing. A linked slide prototype, no-code offline prototype, or numbered text wireflow with an explicit transition table is equally acceptable; every branch must be followable by a reviewer.
3. Create a reusable decision/QA system: field rules, eligibility/capacity rules, state transitions, owner, and checks a teammate can rerun. Apply it to the six supplied test profiles. Record expected and observed states, pass/fail, and any refinement. Then change one design assumption of your choice, rerun at least two affected cases, and explain the result. Do not modify the authoritative product facts.
4. Calculate the supplied baseline conversion rates and set one proposed success metric with a named numerator/denominator, collection event, and owner. Separate a hypothesis from an observed result. No invented forecasts or claim of measured improvement.

Keep scope to one landing experience and one CTA journey. You may defer visual styling or extra channels. Optional stretch: a second headline with an evidence-based experiment hypothesis; it is not needed for full marks.

## Deliverables and acceptance

Submit an archive or repository containing your editable prototype, rules/checks, metric calculation, and a concise handoff. Include an opening file that says how to follow/replay the journey without online accounts. A spreadsheet or text table is valid for checks; code is optional. Include input references next to claims and decisions.

Your work should let a teammate:

- Follow every required branch to an explicit next step without a dead CTA or unsupported capability.
- Reproduce all six profile checks and the two checks after your assumption change, seeing expected versus actual outcomes.
- Find required/optional fields, consent handling, capacity behavior, and who responds when.
- Recalculate all three baseline rates from named counts and identify one measurable proposed goal.
- Use labels, non-color-only errors, readable order, and a text route through the experience.

Add a short decision/work log covering priorities, one obstacle and response, one validation/refinement, remaining limits, and the next step. Add a brief AI-use note naming the tool/task and one output you accepted, corrected, or rejected with your reason; do not fabricate an AI failure, submit full prompt histories, or share personal account access.

Provide a **3–5-minute walkthrough recording or equivalent concise text walkthrough**. The text option earns the same marks. Include where evidence lives, how to replay a case, and one tradeoff.

Prioritize core working states over polish.

## Scoring

Published weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**, total 100. Full marks are available on the core alone. Verification, useful decisions, and follow-through matter; hours worked, writing volume, AI detectors, and prose polish do not.
