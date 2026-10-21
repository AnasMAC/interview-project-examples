# Download remediation verification

A fictional ArchiveKit developer proposed a path-prefix check to prevent exports from leaking outside a tenant directory. The ticket is marked “fixed” after a normal download passed. Independently verify that claim, repair the remaining boundary and leave a regression suite future reviewers can trust.

**Deliberately vulnerable training code:** the proposed fix is incomplete. The model reads only a supplied in-memory file map; it never reads requested paths from your filesystem, starts no server and makes no network calls. Do not test outside the fixture or reuse the starter in production.

## Inputs and setup

- [Proposed implementation and replay CLI](inputs/download.py).
- [Virtual file map](inputs/files.json): synthetic content, no real files requested.
- [Normal smoke requests](inputs/requests.json): intentionally incomplete coverage.
- [Download contract and teammate note](inputs/contract.md).

Baseline skills: basic Python, string/path normalization, write assertions and explain a boundary. Percent encoding is explained in the contract; no exploit framework or prior specialist knowledge is required. Python 3.10+ standard library only. From this project directory, run `python3 inputs/download.py inputs/requests.json` (or your equivalent `python` command). It outputs JSON. You can add a request array with the same fields and pass that filename.

## Core work and acceptance

1. Validate the proposed fix against the contract, using actual local replay. Preserve original output and create a concise verification table with at least two different boundary probes plus legitimate and nonexistent-file controls. Explain why the existing smoke test is insufficient.
2. Repair the path boundary in `download.py`. Preserve legitimate red and blue downloads, including the encoded space filename, and prevent data from outside each tenant root. Keep the file map and contract unchanged.
3. Add a regression suite with at least eight cases using real `download` responses. Include normal downloads for both tenants, encoded legitimate name, sibling-directory prefix, encoded traversal, other-tenant path, missing allowed file and an invalid tenant/absolute/backslash path. Tests must assert status **and** forbidden content absence or correct body. Show relevant tests failing on the original and passing after the repair.
4. Produce a release recommendation (“ready in this model” or “not ready” with reasons), remaining limitations and one next integration check. Your evidence should distinguish a path boundary repair from denying all requests. No web server or actual filesystem implementation is required.

Acceptance: one documented command runs independent tests offline; original exploit evidence is reproducible; denial behavior respects the contract and valid downloads remain usable. Do not claim this proves real-world filesystem/symlink safety. Optional stretch: add a small same-schema mutation test; not required for full marks.

## Submission, AI and timing

Submit an archive or repository containing runnable artifacts, source/evidence references, captured verification output and a concise walkthrough (up to five minutes recording **or equivalent accessible text**). Include exact commands and tool versions. Add a short decision/work log recording prioritization, one obstacle and response, one validation/refinement, limits and next step. Add an AI-use note with one accepted, corrected or rejected output and how you checked it; if no AI was used, say so. Never fabricate an AI failure.

No AI tool is provided: you may use any AI tool you already have. AI is allowed and encouraged for coding, drafting, research, automation and critique. Verify AI output. Tool choice is not graded; free/offline tools are supported, no purchases or personal account access are needed. Synthetic fixtures are the authoritative universe; outside research is optional and cannot affect marks.

Your 24 hours start when you click **Start** on the link in your invitation email; the exercise zip becomes available at that moment. Send your submission back within 24 hours of clicking Start. You are not expected to work for the full 24 hours: organize your own working time and breaks within the window. There are no surprise messages or overnight availability requirements, and hours worked are not scored. The clock tests bounded execution, follow-through and verification, not willingness to sacrifice sleep. Do only this assigned exercise. Full marks are possible on core alone: usable result **40**, accuracy/verification **25**, prioritization **20**, communication/handoff **15**. No AI-detector, writing-volume or prose-polish scoring. Work is an exercise submission, not a company deliverable: no external targets, outreach, production actions or public deployment.
