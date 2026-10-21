# REQ-0061: Integrate Thornscan

| | |
|---|---|
| From | Jonas Albrecht (AppSec lead) |
| Date | 2026-09-22 |
| Priority | High: the trial ends 2026-10-16 |
| Status | Open |
| Attachments | `samples/thornscan/FORMAT.md`, `samples/thornscan/checkout-api/`, `samples/thornscan/route-planner/` |

## Background

We are trialling Thornscan, a SAST tool with data-flow analysis, on the
Python repositories. If it holds up, it replaces Thistle there next quarter
and Thistle's licence is not renewed for those repos. Ewa added a trial job
to the `checkout-api` and `route-planner` pipelines; it ran on 2026-09-22
against the same commits as the last Brackish runs. The two reports and the
vendor's format notes are attached.

Right now the job's output goes nowhere: `ledger ingest` answers
`unknown_format`. To decide on the tool, the teams need to see its results
in Ledger next to Brackish and Thistle, with the same triage, SLAs and
reports.

## What I need

- `ledger ingest` and `POST /api/v1/ingest` accept Thornscan reports, tool
  name `thornscan`, detected from the content like the other formats.
- Its severities mapped to ours. Careful: their `critical` is their second
  level. I would map `blocker` to critical and `critical` to high, but
  tell me if you see a reason not to.
- When Thornscan and Brackish (or Thistle) report the same problem, one
  finding, as for Brackish and Thistle today. Looking at the samples, at
  least the SQL injection in `src/payments/refunds.py:42` and the SSRF in
  `webhooks.py:63` should merge.
- Issues Thornscan reports as suppressed must not show up as open work.
- A report without its `summary` line (the job timed out) must not be
  treated as a clean run; that would mark every Thornscan finding fixed.

## Notes

- Check columns and paths against the format notes before trusting the
  samples: the vendor document has the details, and at least one sample line
  uses an absolute path.
- Priya owns the parsers and wants the usual: samples in `samples/`,
  tests, and an entry in `docs/parsers.md`.
- No schema change should be needed, but say so if you disagree.

## Comments

**Mateo Rojas, 2026-09-23 09:12 +02:00.** Dedupe side: Thornscan is SAST,
so it gets the same issue key as Brackish and Thistle, `path:line:CWE-<n>`
with the normalized path, the 1-based line and the *primary* CWE, which per
the format notes is the first entry of `cwe`. An empty `cwe` means no issue
key and so no cross-tool merge, same as a SARIF result without a CWE. Please
do not change the fingerprints or issue keys of the other tools, and leave
`FINGERPRINT_VERSION` at 1: every stored row depends on them. If you think
the key should work differently for Thornscan, write it up for Jonas. The
key is shared by all three tools, so that is his call, not a parser detail.

**Priya Raman, 2026-09-23 10:40 +02:00.** For the parser: Ledger stores
repo-relative paths and 1-based columns for every tool (we already shift
Thistle before 5.0); Thornscan's `col` is 0-based. And detection from the
content, please, like the other formats: the trial job writes
`thornscan.jsonl`, but the shared CI template uploads whatever name the job
gives it.

**Ewa Kowalczyk, 2026-09-30 08:50 +02:00.** The trial job ran again on
2026-09-29, now with Thornscan 1.5.0; both files are attached next to the
first ones. `checkout-api/thornscan-2026-09-29-b33ee32.jsonl` is a week of
changes later (commit `b33ee329d5425504bbc9cabe5ff6de367db2d63e`). The
route-planner job timed out after 10 minutes (commit
`a679052932dad3c410ba8d395ec7d8b4dbf13294`); I attached its file anyway, it
is what Thornscan had written when the runner stopped it.
