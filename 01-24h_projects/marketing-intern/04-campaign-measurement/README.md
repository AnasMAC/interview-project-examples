# A campaign measurement desk

The fictional product TriageLane ran two small demo-request campaigns. A draft summary recommends the wrong winner because imports, event definitions, and campaign tags need attention. Build a refreshable measurement desk, verify it on a second export, and recommend one bounded next experiment.

## Start, tools, and scope

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded execution and verification, not motivation.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for formulas, data cleaning, critique, automation, and checking. No purchase is needed. Free/offline spreadsheet tools or a documented manual rule system are acceptable; code optional, tool choice not graded. If using code, provide local run instructions with no services. Check AI-generated formulas and assumptions. Optional external research adds no marks and cannot define fictional data. No accounts, ads, publication, real tracking, or production access.

Baseline skills: reading CSV, basic percentages/division, and spreadsheet formulas or clear tables. The local dictionary defines all metrics; security expertise is unnecessary.

## Inputs and setup

Keep the raw inputs unchanged. Import CSVs with a header row, retaining IDs and currency labels.

- [Product, dictionary, and metric rules](inputs/data-dictionary.md).
- [Baseline export](inputs/baseline.csv).
- [Second export](inputs/refresh.csv) to test the same system on new input.
- [Draft summary and experiment constraints](inputs/decision-brief.md).

All rows and costs are synthetic. Missing/invalid data should remain visible in an exception ledger, with a reason and next-step owner. Do not repair unsupported values by guessing.

## Core work

1. Build a reusable measurement workbook or equivalent explicit rule system. Preserve raw data; create cleaned, duplicate, quarantined, and unattributed views/ledgers; document rules and stable IDs. A teammate must be able to add the second export and reproduce results without manually inventing a new answer. Manual systems must give exact calculation steps and show their second run.
2. For the valid baseline, calculate by named campaign and overall valid data: sessions, CTA starts, valid requests, qualified requests, attributable spend, CTA-start/session rate, valid-request/session rate, qualified-request/session rate, spend/valid-request, and spend/qualified-request. Keep unattributed activity visible rather than allocating it to a favored campaign. State excluded/quarantined spend separately. Explain how denominators and zero cases work.
3. Produce a concise decision view: compare campaign outcomes/costs, correct the supplied draft summary, separate observed evidence from hypotheses, and choose one next experiment within the brief's constraints. Specify hypothesis, audience, one changed variable, primary metric with numerator/denominator, guardrail, decision rule, and important uncertainty. No causal claim or reliable forecast from these small aggregates.
4. Demonstrate checks: duplicate handling, event-count hierarchy, missing campaign, metric denominator, and zero denominator. Record expected versus actual output, pass/fail, and a correction/refinement. Run the same system on the second export and show the **incremental** and **combined** valid results and exceptions. Rerun one affected check after refinement. Formulas, visible intermediate calculations, or local commands are all acceptable reproducible evidence.

Core scope is two small CSVs, one refreshable measurement artifact, one decision view, and one experiment. Optional stretch: a chart or scenario slider; unnecessary for full marks and cannot replace validation.

## Submission and acceptance

Submit an archive or repository with opening instructions, editable measurement artifact, preserved raw inputs, cleanup/exception ledger, decision view and experiment, and check/replay log. A teammate should be able to:

- Refresh using the provided second export and reproduce both incremental and combined views.
- Identify duplicates/quarantines/unattributed rows without data silently disappearing.
- Recompute rates/costs using the correct cohorts and see `not applicable` for undefined division.
- Trace the recommendation to calculations and constraints while preserving uncertainty.
- Find expected/actual results for five check types and an affected rerun.

Include a short decision/work log: priorities, one obstacle and response, one validation/refinement, limits, next step. Include an AI-use note with one accepted/corrected/rejected output and reason; do not fabricate a failure, expose accounts, or submit full prompt histories. Give a **3–5-minute recording or equivalent concise text walkthrough**, equally acceptable.

Correct refresh behavior matters more than dashboard polish.

## Scoring

Weights: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**, total 100. Core alone can earn full marks. No grading of hours, AI detectors, prose polish, or volume.
