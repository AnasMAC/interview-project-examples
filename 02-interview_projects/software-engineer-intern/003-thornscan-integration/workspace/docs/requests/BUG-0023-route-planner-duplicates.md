# BUG-0023: route-planner findings duplicated after the repository moved

| | |
|---|---|
| From | Lucas Moreau (developer, Routing) |
| Date | 2026-09-18 |
| Priority | High: our SLA numbers doubled overnight |
| Status | Open |

## Report

> On Monday (2026-09-14) the platform team moved our repository from
> `git.fernwick.example.test/routing/route-planner` to
> `git.fernwick.example.test/logistics/route-planner` (the new Logistics
> group). Old URLs redirect, the pipeline was not changed, and builds are
> green.
>
> Since then Ledger shows most of our code findings twice. The old ones
> went to `fixed` after the first pipeline run on the new path, and the
> same issues came back as `new` with a fresh SLA, no triage and no
> history. The two false positives we triaged last month are back as
> untriaged. Dependency and Kitewatch findings look fine.
>
> I compared two occurrences of the same Thistle finding in the API:
>
> - before: `raw_location` = `file:///builds/routing/route-planner/planner/cache.py:88:4`
> - after: `raw_location` = `file:///builds/logistics/route-planner/planner/cache.py:88:4`
>
> The CI workspace path changed with the group. Nothing else in the report
> changed, and the commit is the same between two of the runs. Our `OWNERS`
> file did not change.
> -- Lucas

## Notes from AppSec (Mateo Rojas)

- Ledger still has the repository as `routing/route-planner`
  (`repos.full_name`); nobody told us about the move.
- The duplicates are real rows: each "new" finding has its own fingerprint
  and its own occurrences. Ingest logs for the affected runs are in
  journald (`ingest.done` lines with high `new` and `fixed` counts).
- Two more repositories move into Logistics in October (`eta-service` and
  `slotting-engine`). Whatever we do has to work for them too.
- Fixing the code is half of it. Routing also wants their history and
  triage back on the findings they had before; we have not cleaned up the
  database yet. Please propose how, and do not lose events.
