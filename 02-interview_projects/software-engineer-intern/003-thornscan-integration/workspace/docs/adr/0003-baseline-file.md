# ADR 0003: Suppressions live in a baseline file in the repository

- Status: Accepted
- Date: 2025-10-06
- Deciders: Mateo Rojas, Jonas Albrecht, Samuel Okafor

## Context

Some findings are correct but not worth fixing: test fixtures with dummy
keys, vendored SDKs reviewed on upgrade, a debug page that is only reachable
from the office VPN until the next release. Before 1.5 teams marked them
`false_positive`, which was wrong and lost the reason, or asked AppSec to
delete rows, which came back on the next scan.

We wanted suppressions to be reviewed like code, to sit next to the code
they describe, to expire, and to work the same for every tool.

## Decision

Each repository may contain `.ledger-baseline.json` at its root. Ledger
reads it on every ingest (for the sample repositories,
`samples/repos/<repo>/.ledger-baseline.json`).

```json
{
  "version": 1,
  "suppressions": [
    {"tool": "brackish", "rule": "BRK-SECRET-004", "path": "tests/fixtures/**",
     "reason": "Dummy gateway keys used by the refund tests", "ticket": "SEC-214",
     "added_by": "mrojas", "expires": "2026-12-31"}
  ]
}
```

- `reason` is required. At least one of `rule`, `path` or `fingerprint` is
  required, so an entry can never suppress a whole tool. `tool`, `ticket`,
  `added_by` and `expires` are optional. Unknown keys are a parse error, so
  typos do not silently suppress nothing.
- `path` is a glob anchored at the repository root: `*` matches within one
  path segment, `**` across segments, a trailing `/` matches everything
  below a directory. Unlike OWNERS, a pattern without `/` does **not** match
  at any depth.
- `expires` is the last valid day (UTC). After it, the entry no longer
  matches and the finding is unsuppressed on the next sighting.
- The first matching entry wins; its reason is stored in
  `findings.suppression_reason`.
- A suppressed finding is still a finding: it is stored, keeps its history
  and occurrences, and gets `suppressed` / `unsuppressed` events. Reports,
  team summaries and SLA checks leave it out.
- Suppression is synchronized only on sightings from the finding's own tool.

## Consequences

- Changes go through the team's normal code review; CODEOWNERS can require
  an AppSec reviewer for `.ledger-baseline.json`.
- History is in Git: who suppressed what, when and why.
- Expiry forces a second look instead of permanent silence.
- Ledger reads baselines (and OWNERS files) from its repositories directory,
  `samples_dir/repos/<repo>/`. Locally that is `samples/repos/`; on the
  shared instance a sync job copies each repository's default-branch files
  there every 15 minutes. A suppression added on a branch therefore applies
  only after it is merged, and a scan on an old release branch uses the
  current baseline of `main`.
- `false_positive` triage stays for findings that are simply wrong.
