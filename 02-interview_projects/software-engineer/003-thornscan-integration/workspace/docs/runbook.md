# Runbook

Owner: Ewa Kowalczyk (platform). For whoever is on Ledger duty that week.
Questions: `#appsec-ledger`.

## Where things run

| What | Where |
|---|---|
| Shared instance | `ledger.int.fernwick.example.test`, one VM, API on port 8765 behind the internal proxy |
| Database | `/srv/ledger/var/ledger.db` (local volume; never on NFS, see ADR 0001) |
| Repositories dir | `/srv/ledger/repos/<repo>/` (OWNERS and `.ledger-baseline.json`, synced from each default branch every 15 min) |
| Logs | journald, unit `ledger-api`; JSON lines (`LEDGER_LOG_FORMAT=json`) |
| Tokens | `LEDGER_READ_TOKEN`, `LEDGER_ADMIN_TOKEN` from the platform secret store; the values in `config/ledger.toml` are DEMO only |
| Weekly reports | cron, Monday 06:30 Leipzig time: `ledger report --week <last Monday> --team <slug> --format html` per team, mailed to the managers |

## Local setup

```sh
make setup      # var/ledger.db: migrations + demo seed (8 teams, 14 repos, ~3,000 findings)
make demo       # ingests samples/ into checkout-api and route-planner (branch main)
make run-api    # 127.0.0.1:8765
```

The seed leaves `main` of `checkout-api` and `route-planner` empty so that
`make demo` shows the sample history on its own; their seeded findings are
on release branches. Demo history ends on 2026-09-23. With the wall clock,
everything looks older and more overdue; set
`LEDGER_NOW=2026-09-23T14:00:00+02:00` to see it as of that day.

`make seed SCALE=17` builds about 51,000 findings for performance work;
`make bench` prints ingest and report timings on throw-away databases.

## Routine tasks

**Migrations.** After deploying a new version: `python3 -m ledger migrate`.
The CLI refuses to run other commands while migrations are pending. The
runner refuses a migration file whose checksum changed after it was applied:
never edit a shipped file, add a new one.

**Backups.** Nightly at 02:00: `sqlite3 /srv/ledger/var/ledger.db ".backup
/srv/backup/ledger-$(date +%F).db"`. `.backup` is safe while the API runs;
copying the file with `cp` is not (WAL). Restore: stop the API, copy the
backup to `ledger.db`, delete `ledger.db-wal` and `ledger.db-shm`, start.

**Token rotation.** Generate a new value, update the secret store, restart
`ledger-api`. Tell the dashboard team before rotating the read token.

**Holidays.** `config/holidays.toml` holds one year of Saxony public
holidays. Add the next year before December: SLA due dates in a year
without holidays count only weekends (Ledger logs `sla.holidays_missing`
once per year and loaded calendar, so once per ingested file whose due dates
reach that year). 2027 is not in yet.

## When something breaks

**A CI ingest failed.** The job log shows `FAIL <file>: <message>`.

- `parse_error` (422): the report is damaged or a new scanner version
  changed the format. Get the file from the job artifacts and try it
  locally with `python3 -m ledger ingest --repo ... --branch ... --commit
  ... FILE` against a copy of the database. New format: ticket for Priya.
- `unknown_format` (415): no parser recognises the file; usually the job
  uploaded the wrong artifact (an HTML report instead of JSON).
- `conflict` (409): the same file was already ingested for that commit.
  Harmless on job retries.
- `not_found`: the repository is not registered in `repos`.

Each file is its own transaction, so one failed file never leaves half a run
behind and the other files of the job are stored.

**"database is locked".** A writer held the lock for more than the 5 s busy
timeout: usually a manual long `sqlite3` session or a large backfill.
Find it, end it, let CI retry. Never raise the timeout to hide it.

**Findings fixed and re-created in bulk.** Usually a path change: a CI
runner move, a repository moved to another group, or a scanner switching
between relative and absolute paths. Compare `occurrences.raw_location` of
an old and a new sighting of the same issue, then check
`ledger/normalize/paths.py`. Do not delete rows; history and triage live on
the old findings.

**A team says a finding belongs to someone else.** Check the repository's
`OWNERS` file (the last matching rule wins), fix it in the repository, and
wait for the sync. Only findings first seen after that get the new team;
existing ones keep the team they were assigned on insert. Move those with a
reviewed one-off `UPDATE findings SET team_id = ...` and post it in
`#appsec-ledger`.

**`sla-check` fails CI for a team.** That is its job (exit 1 when breaches
exist). `ledger sla-check --team <slug>` lists them; the way out is a fix,
a triage decision, or a baseline entry with a reason, not a pipeline change.

## Useful queries

```sql
-- runs of the last day
SELECT r.name, u.branch, u.tool, u.raw_count, u.new_count, u.fixed_count, u.ingested_at
FROM runs u JOIN repos r ON r.id = u.repo_id
WHERE u.ingested_at >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-1 day') ORDER BY u.ingested_at;

-- history of one finding
SELECT kind, from_value, to_value, actor, note, created_at FROM finding_events
WHERE finding_id = ? ORDER BY created_at, id;
```
