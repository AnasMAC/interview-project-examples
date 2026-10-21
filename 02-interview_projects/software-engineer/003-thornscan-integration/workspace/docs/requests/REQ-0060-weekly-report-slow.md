# REQ-0060: Weekly report is too slow on the shared instance

| | |
|---|---|
| From | Ewa Kowalczyk (platform) |
| Date | 2026-09-21 |
| Priority | Medium; blocks the dashboard work planned for Q4 |
| Status | Open |

## What happens

The Monday cron (`ledger report --week <last Monday> --team <slug>`, Markdown
and HTML for each of the 8 teams, 16 runs) took **2 min 41 s** this morning
on the shared instance. In March it took about 20 s. While it runs, the API
answers slowly too: the dashboard's team page timed out twice at 06:35.

The shared instance has about 50,000 findings now (Warehouse alone has
about 14,000 since `wms-core` got Thistle), and much more history than the
demo data: 18 months of CI runs, about 1.6 million occurrences and 700,000
finding events. Findings that flap between fixed and reopened on busy repos
have hundreds of events each.

## Reproduce locally

```sh
make seed SCALE=17     # ~51,000 findings, 10 weeks of history
make bench             # times the weekly report on a scale-17 database
python3 -m ledger report --week 2026-09-21 --format html --out /tmp/weekly.html
```

On my laptop one all-teams report takes about 1.2 s and the 16 cron runs
about 3.5 s at SCALE=17. That is much faster than the VM (smaller history,
warm local SSD), but if you profile it the shape is the same. The seed has
weekly runs only; if you want history closer to the shared instance, more
events per finding is the knob.

## What I need

- The 16 cron runs well under a minute on the shared instance; I will
  measure there, you measure locally and tell me the factor.
- The dashboard team (Q4) wants the per-team weekly numbers on demand from
  the API. Their budget is **300 ms per team** at 50k findings, so a fix
  that only works for a nightly batch is not enough.
- Same output as today. Samuel uses the Monday numbers in the managers'
  meeting, so if a number changes, explain why.
- No new dependencies (ADR 0001). New indexes are fine through a migration.

Please put before/after numbers from `make bench` in the PR.
