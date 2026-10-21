# Local asset search with composable filters and stable pagination

This is one Software Engineer assessment with a **24-hour** window. Your recruiter assigns one exercise, never all five. Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. Follow-through and verification matter more than hours or volume.

A fictional analyst has a small offline asset inventory and needs predictable search instead of manually editing JSON. Implement a CLI query engine whose text search, filters, sorting and pagination compose, while invalid inventory rows and another tenant cannot silently distort results.

All companies, tenants, assets and product behavior here are **fictional assessment facts**. The supplied fixtures are the authoritative universe. Outside research is optional and cannot affect marks. Do not contact real systems, send real messages, publish, or use production credentials.

## Supplied inputs and setup

You need basic Python, JSON, CLI use, tests, and familiarity with composable predicates, schema validation, tenant boundaries, deterministic sorting, and pagination math. Python **3.10 or later**, its standard library, and any local editor are sufficient; no packages, accounts, paid tools, web access or company framework are needed.

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

The initial smoke suite should pass. The last command should print `STARTER: implement search_assets` to stderr, return **3**, and produce no stdout. This is intentional, not a setup failure. The starter neither solves the feature nor provides a completed output. Replace the placeholder behavior and replace its smoke assertion with feature assertions; keep the help/file-error checks. You may restructure code, but preserve documented CLI options and make the README run commands accurate.

## Core task and observable acceptance criteria

Build a usable feature implementing the following contract. Use JSON on stdout for successful runs, readable diagnostics on stderr for fatal errors, and the documented exit codes. Explain any assumptions without silently changing the rules.

- Input object has `assets` array. Asset fields are nonempty string tenant/asset_id/name/hostname; tags is an array of nonempty strings; status is active/archived; risk is an integer from 0 through 100, excluding booleans. Trim string fields; repeated tags are deduplicated. Tenant and asset ID remain case-sensitive.
- Scope to --tenant before validation/search. Exclude foreign rows and expose only their count `excluded_foreign_rows`, never their names/hostnames. Diagnose invalid selected-tenant rows with one-based row and reason and omit them. Duplicate asset IDs within selected tenant invalidate every occurrence; diagnose every affected row.
- --query is a case-insensitive literal substring of name OR hostname (trim query; empty means all). No regex or external lookup. --tag can repeat: every requested tag must be present, case-insensitively. --status is exact. --min-risk is inclusive. All filters combine with AND; perform filtering before pagination.
- --sort name: ascending (casefolded name, asset_id). --sort risk: descending risk, then ascending asset_id; equal risks must be deterministic independent of input order.
- --page is one-based positive integer; --page-size is 1..50; --min-risk is 0..100. Invalid query parameters fail with exit 2 and readable errors. An out-of-range positive page succeeds with no items and unchanged total.
- Output `items` with normalized selected asset fields; `total` matching rows before pagination; `page,page_size,total_pages` (0 when total 0); `diagnostics` for invalid selected rows; `excluded_foreign_rows`. Search returns exit 0 even with invalid rows and never changes inventory.
- File/top-level errors exit 2. Empty assets or zero matches return empty items. No web UI, database, network service or performance benchmark is required.

Run primary with --query api --tag prod --status active --min-risk 50 --sort risk --page-size 1: total 2, first a1, second page a2. No foreign asset fields appear; bad1 is diagnosed. Add tests for AND tags, inclusive risk=0, tied sorting after reversing input, empty/out-of-range pages, invalid parameters and second inventory.

Add meaningful automated checks that test results and errors, not just that code runs. Include at least one boundary case you construct, and one failing case you fix or a validation that causes a refinement. A clear, tested core earns full marks. Optional stretch: improve the local developer experience or add a useful extra test; no stretch is necessary. A web service, full framework, database, public deployment, or large architecture is outside the core scope.

After implementing the core, use these exact local verification runs. Initially every valid fixture invocation returns the documented exit-3 placeholder; after implementation, each should succeed and match the criteria above.

```sh
python3 app.py --input inputs/primary.json --query api --tag prod --status active --min-risk 50 --sort risk --page-size 1
python3 app.py --input inputs/primary.json --query api --tag prod --status active --min-risk 50 --sort risk --page-size 1 --page 2
python3 app.py --input inputs/secondary.json --sort risk --page-size 3
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
