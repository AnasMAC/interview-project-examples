# ADR 0002: Cross-tool deduplication of SAST findings

- Status: Accepted
- Date: 2025-06-02
- Deciders: Mateo Rojas, Jonas Albrecht, Priya Raman

## Context

With Ledger 1.3 we added Thistle next to Brackish. Both are SAST tools and
both scan every Python repository, so most real problems are reported twice:
Brackish says `BRK-SQLI-001` at `src/payments/refunds.py:42`, Thistle says
`TH-INJ-SQL` at the same place. Teams saw two findings, triaged them twice,
and the weekly report counted the problem twice against their SLA numbers.

Each tool's own fingerprint (tool, rule, location) cannot merge these: the
tools use different rule ids and neither knows the other's catalogue.
Mapping rule ids between tools by hand was rejected: Brackish has about 300
rules, Thistle about 450, and both add rules every release.

## Decision

SAST findings get a second key next to the fingerprint, the **issue key**,
built from the normalized location only:

```
issue_key = "<repo-relative path>:<line>"
```

It is set for code findings from `brackish` and `thistle` that have a line,
and NULL otherwise (DAST, dependency and pentest findings are not merged).

On ingest, a SAST finding whose fingerprint is unknown but whose issue key
matches an existing finding of **the other SAST tool** on the same repo and
branch is merged into that finding:

- the sighting is stored as an occurrence of the existing finding, with the
  reporting tool's own rule id and severity;
- a `merged` event records which tool and rule were folded in;
- no new finding is created, so triage and the SLA clock stay with the
  first report.

The finding keeps the tool that reported it first (`findings.tool`). Only
runs of that tool can mark it fixed: a Thistle run that no longer reports
the problem does not close a Brackish finding.

## Consequences

- Teams see one finding per problem and triage it once.
- A line shift in one tool's output (Thistle used to report the line of the
  enclosing call) prevents a merge. We accept duplicates there rather than
  merging by fuzzy distance.
- The merge depends on path normalization: both tools must produce the same
  repo-relative path, which is why Thistle's absolute workspace URIs are
  stripped in `ledger/normalize/paths.py`.
- Two different problems on the same line are merged. We expect this to be
  rare.
- A third SAST tool joins the same scheme by being added to the SAST tool
  list; no mapping table is needed.
