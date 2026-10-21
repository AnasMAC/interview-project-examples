# REQ-0062: Show the commit a finding was first seen in

| | |
|---|---|
| From | Lucas Moreau (developer, Routing) |
| Date | 2026-09-22 |
| Priority | Low |
| Status | Open; Samuel agrees, the API part needs Jonas's review |

## Request

> When a new finding shows up in the weekly report, the first thing we do is
> look for the change that introduced it. Today we open the finding in the
> dashboard, take the first-seen date, and dig through `git log` around that
> date for the repository. On busy repos that is 30-40 merges a day.
>
> Ledger knows which pipeline run first reported a finding, and each run has
> a commit. Could the finding show that commit (and ideally a link to it on
> `git.fernwick.example.test`) in:
>
> - `GET /api/v1/findings` and `GET /api/v1/findings/{id}`,
> - `ledger findings --json`,
> - the weekly report's oldest-findings table and the CSV export?
>
> For reopened findings, the commit where it came back is the interesting
> one.
> -- Lucas

## Notes from Samuel

- "First seen in commit" is the commit of the first run that reported it,
  not necessarily the commit that introduced the problem: scans run per
  pipeline, Kitewatch scans staging, and pentest reports have no real commit.
  The name and the docs must not promise more than that.
- Findings merged across tools: the finding's first run is enough.
- Commits are stored as given by CI (7 to 40 hex characters). A short SHA
  is fine for display; links need the full one if we have it.
- The dashboard team parses the findings list; adding fields is fine,
  renaming or removing is not.
- Older findings imported before 1.2 (ingest without `--commit`) have
  placeholder commits on the shared instance; decide what the field shows
  for them.
