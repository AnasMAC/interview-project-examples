# Finding snapshot diff with incomplete scan coverage

This is one Software Engineer assessment with a **24-hour** window. Your recruiter assigns one exercise, never all five. Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Follow-through and verification matter more than hours or volume.

A fictional scan dashboard currently labels every missing finding as resolved. A partial scan can make that conclusion false. Build a diff that distinguishes new, severity-changed, unchanged, resolved, and unknown findings, then produce a compact human report from the same result.

All companies, tenants, assets and product behavior here are **fictional assessment facts**. The supplied fixtures are the authoritative universe. Outside research is optional and cannot affect marks. Do not contact real systems, send real messages, publish, or use production credentials.

## Supplied inputs and setup

You need basic Python, JSON, CLI use, tests, and familiarity with stable identity, snapshot comparison, uncertainty preservation, tenant isolation, and report consistency. Python **3.10 or later**, its standard library, and any local editor are sufficient; no packages, accounts, paid tools, web access or company framework are needed.

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

The initial smoke suite should pass. The last command should print `STARTER: implement diff_snapshots` to stderr, return **3**, and produce no stdout. This is intentional, not a setup failure. The starter neither solves the feature nor provides a completed output. Replace the placeholder behavior and replace its smoke assertion with feature assertions; keep the help/file-error checks. You may restructure code, but preserve documented CLI options and make the README run commands accurate.

## Core task and observable acceptance criteria

Build a usable feature implementing the following contract. Use JSON on stdout for successful runs, readable diagnostics on stderr for fatal errors, and the documented exit codes. Explain any assumptions without silently changing the rules.

- Input has `tenant`, `before.findings`, `after.findings`, and `after.coverage`. Selected tenant must equal the input tenant. Finding fields are nonempty strings `tenant,asset_id,rule_id,location,evidence` and severity in critical/high/medium/low/info. Trim string fields and lowercase severity; preserve trimmed location identity.
- Scope to the selected tenant before comparing. Exclude foreign-tenant rows and report only their count in `excluded_foreign_rows`, never their values/evidence. Invalid selected-tenant rows or duplicate selected-tenant keys within a snapshot fail the request (exit 2); do not invent a merge policy.
- Finding identity is `(tenant,asset_id,rule_id,location)`. For a key in after only, classify new. In both: severity difference means changed; otherwise unchanged, even when evidence text changes. Include before/after severity and evidence as applicable.
- For a key in before only, classify resolved only if that asset has `complete` after coverage; otherwise unknown. Coverage statuses are complete/partial/failed; a missing entry also means unknown. Coverage asset IDs must be unique, nonempty, and statuses valid or exit 2.
- Output `entries` sorted by key with key fields, `classification`, `before_severity,after_severity,before_evidence,after_evidence` (null when absent); `counts` for all five classes, `excluded_foreign_rows`, and `report` as a readable multiline string. Report counts and group entries by classification using the same data; do not make external claims.
- Empty snapshots and unknown coverage are valid. Malformed files/top-level schemas exit 2 with readable errors and no success output. Repeat runs must match. No network, database, HTML interface, or vulnerability research required.

Primary counts must be new 1, changed 1, unchanged 1, resolved 1, unknown 1, with 2 foreign rows excluded. Add tests for incomplete/missing coverage, severity vs evidence-only changes, duplicate keys, empty snapshots and tenant isolation. Secondary yields one unknown, zero resolved.

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
