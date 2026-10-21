# Changelog

Ledger, the Fernwick AppSec findings ledger. Dates are release dates on the
shared instance. Handles are in `CODEOWNERS`.

## 2.4.1 (2026-09-15)

- Fixed: OWNERS patterns with a trailing `/` matched files whose name merely
  started with the directory name (`/src/checkout/auth/` matched
  `src/checkout/authz.py`) (@sokafor).
- Fixed: CSV export did not guard cells starting with a tab or carriage
  return against formula injection (@sokafor).
- Fixed: `ledger ingest --manifest` stopped at the first failed file instead
  of reporting it and going on (@ekowalczyk).

## 2.4.0 (2026-09-01)

- Added: SLA due dates in business days, Monday to Friday minus Saxony
  public holidays (`config/holidays.toml`, Europe/Berlin calendar). Before,
  due dates counted calendar days in UTC. Existing due dates were not
  recomputed (@sokafor).
- Added: report weeks and business days use local time (`LEDGER_TIMEZONE`);
  a finding first seen at 00:30 on a Monday in Leipzig belongs to that week.
- Added: `LEDGER_NOW` freezes the clock for a CLI or API process, for demos
  and reproducible CI reports (@jalbrecht).
- Added: log formatters redact bearer values and `ldg-*` tokens (@jalbrecht).
- Added: `ledger seed --scale N` and `make bench` for performance work
  (@ekowalczyk).

## 2.3.1 (2026-07-06)

- Fixed: Thistle 4.x writes 0-based `startColumn`; columns are now stored
  1-based for both SAST tools (@praman).

## 2.3.0 (2026-06-15)

- Changed: **the cross-tool issue key now includes the CWE**
  (`path:line:CWE-<n>`). With path and line only, a SQL injection and a
  hard-coded secret on the same line of `payouts-worker` were merged into
  one finding, and fixing one closed both. SAST findings without a CWE no
  longer merge across tools. Issue keys of open findings were recomputed by
  a one-off script on the shared instance (@mrojas).
- Added: Thistle `originalUriBaseIds` are resolved before path
  normalization (@praman).

## 2.2.0 (2026-04-20)

- Added: Kitewatch 3 reports. The parser reads both schemas: v2 with numeric
  `risk` 1-5 and v3 with word severities (`Critical`, `High`, `Medium`,
  `Low`, `Info`). Several teams still run Kitewatch 2.9 (@praman).
- Added: `GET /api/v1/teams` with open counts and breaches per team
  (@jalbrecht).

## 2.1.0 (2026-02-09)

- Added: HTML weekly report and CSV export (`ledger report --format
  html|csv`) (@sokafor).
- Changed: ingest runs one transaction per file and starts it with
  `BEGIN IMMEDIATE`; WAL and a 5 s busy timeout are always on. Two CI jobs
  ingesting at once used to fail with "database is locked" (@ekowalczyk).
- Fixed: pentest CSV files re-saved by old Excel versions (Windows-1252)
  failed to import (@praman).

## 2.0.0 (2025-12-01)

- Changed: **findings are tracked per repository and branch**. A scan of a
  feature branch no longer fixes or reopens findings of `main` (@mrojas).
- Changed: the API moved to `/api/v1/` with read and admin tokens; the
  unauthenticated 1.x endpoints are gone (@jalbrecht).
- Changed: the 14 migration files of 1.x were squashed into
  `0001_initial.sql`. The shared instance was stamped with a one-off script;
  databases older than 1.6 must be rebuilt (@jalbrecht).
- Removed: `ledger export-json`; use the API.

## 1.6.0 (2025-11-03)

- Added: triage history in `finding_events` (kinds `new`, `fixed`,
  `reopened`, `triage`, `suppressed`, `unsuppressed`, `merged`)
  (migration 0012) (@mrojas).
- Added: `ledger sla-check` exits 1 when breaches exist, for CI gates
  (@sokafor).

## 1.5.0 (2025-10-13)

- Added: baseline suppressions from `.ledger-baseline.json` in each
  repository (ADR 0003, migration 0010 adds `findings.suppressed`)
  (@mrojas).

## 1.4.0 (2025-08-25)

- Added: pentest report import from CSV, written by Ines Duarte during her
  internship (@praman).
- Added: triage through the API, `confirmed`, `false_positive`,
  `accepted_risk` (migration 0008) (@jalbrecht).

## 1.3.0 (2025-06-16)

- Added: Thistle SARIF reports and cross-tool deduplication of SAST findings
  at the same path and line (ADR 0002, migration 0006 adds `issue_key`)
  (@mrojas, @praman).
- Added: read-only HTTP API (@jalbrecht).

## 1.2.0 (2025-04-14)

- Added: SLA policy per severity (`config/sla.toml`) and `due_at`
  (migration 0004) (@sokafor).
- Changed: `ledger ingest` requires `--commit` (@ekowalczyk).

## 1.1.0 (2025-03-17)

- Added: Kitewatch JSON reports (@praman).
- Added: team ownership from the `OWNERS` file of each repository, falling
  back to the repository's team (@sokafor).

## 1.0.0 (2025-02-10)

- First release: `ledger ingest` for Brackish SARIF and Depwarden XML,
  fingerprints per tool, new/open/fixed lifecycle, weekly Markdown report
  per team, SQLite storage (ADR 0001) (@jalbrecht, @mrojas, @praman,
  @ekowalczyk, @sokafor).
