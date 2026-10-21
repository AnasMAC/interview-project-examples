# Finding importer with validation and evidence merging

This is one Software Engineer Intern assessment with a **24-hour** window. Your recruiter assigns one exercise, never all five. Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Follow-through and verification matter more than hours or volume.

The fictional North team receives scanner exports with inconsistent severity names, duplicates, and rows from another tenant. Build a reusable batch importer so a reviewer can see valid consolidated findings and understand every rejected row.

All companies, tenants, assets and product behavior here are **fictional assessment facts**. The supplied fixtures are the authoritative universe. Outside research is optional and cannot affect marks. Do not contact real systems, send real messages, publish, or use production credentials.

## Supplied inputs and setup

You need basic Python, JSON, CLI use, tests, and familiarity with validation, stable identity, severity ordering, data merging, and row-level diagnostics. Python **3.10 or later**, its standard library, and any local editor are sufficient; no packages, accounts, paid tools, web access or company framework are needed.

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

The initial smoke suite should pass. The last command should print `STARTER: implement import_findings` to stderr, return **3**, and produce no stdout. This is intentional, not a setup failure. The starter neither solves the feature nor provides a completed output. Replace the placeholder behavior and replace its smoke assertion with feature assertions; keep the help/file-error checks. You may restructure code, but preserve documented CLI options and make the README run commands accurate.

## Core task and observable acceptance criteria

Build a usable feature implementing the following contract. Use JSON on stdout for successful runs, readable diagnostics on stderr for fatal errors, and the documented exit codes. Explain any assumptions without silently changing the rules.

- Input is an object with `tenant`, an `assets` array of allowed asset IDs, and `records`. The selected CLI tenant must equal the input tenant or the entire request fails with exit 2.
- Each row needs nonempty string `source_id, tenant, asset_id, rule_id, location, severity, evidence`; trim strings. Tenant and asset membership are case-sensitive. Reject wrong tenant, unknown asset, missing fields, non-string fields, blank values, or severity outside critical/high/medium/low/info after trimming and lowercasing.
- Keep invalid rows out of findings but include one diagnostic per invalid source row with one-based `row`, original `source_id` when available, and a readable `reason`. If several rules fail, one clear reason is enough.
- Deduplicate by the trimmed tuple `(tenant, asset_id, rule_id, location)`. Preserve the location text exactly after trimming; ports, paths and schemes are significant. Merge sorted unique evidence strings and source IDs. Keep the highest severity using critical > high > medium > low > info.
- Output `findings` (each with the key fields, normalized severity, `evidence` and `source_ids` arrays), `rejected` diagnostics, and `summary` with `input_rows, accepted_rows, unique_findings, duplicate_rows, rejected_rows`. Accepted rows include valid duplicates. Sort findings by the key tuple; diagnostics follow input row order.
- A valid batch containing rejected rows still exits 0. Bad top-level schema, unreadable files or malformed JSON exit 2 with a readable error and no successful output. Empty record arrays return empty arrays and zero counts.
- Re-running a batch produces identical output and never changes the input. Both batches are independent; no database or incremental import is required.

Primary: 10 input rows, 5 accepted, 3 unique findings, 2 duplicate rows, 5 rejected rows. Add tests for merged evidence/severity, tenant rejection, exact location identity, empty batch and malformed input. Secondary: independently process the second fixture and reconcile every row.

Add meaningful automated checks that test results and errors, not just that code runs. Include at least one boundary case you construct, and one failing case you fix or a validation that causes a refinement. A clear, tested core earns full marks. Optional stretch: improve the local developer experience or add a useful extra test; no stretch is necessary. A web service, full framework, database, public deployment, or large architecture is outside the core scope.

After implementing the core, use these exact local verification runs. Initially every valid fixture invocation returns the documented exit-3 placeholder; after implementation, each should succeed and match the criteria above.

```sh
python3 app.py --input inputs/primary.json --tenant north
python3 app.py --input inputs/secondary.json --tenant north
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
