# Ledger architecture

Owner: Jonas Albrecht (AppSec lead). Last reviewed for 2.4.0 (2026-09).

Ledger collects the reports our CI scanners produce, turns them into one
deduplicated list of findings per repository and branch, assigns each finding
to the owning team, tracks its remediation SLA and produces the weekly team
reports. It is a single Python package with no third-party runtime
dependencies, backed by one SQLite file. Why SQLite: `docs/adr/0001-sqlite.md`.

```
CI job ──report file──> ledger ingest (CLI)  ─┐
dashboard / scripts ──> POST /api/v1/ingest  ─┤
                                              v
     parsers ──RawFinding──> normalize ──> dedupe (fingerprint, issue key,
     (detect + parse)        (paths,        baseline, lifecycle) ──> SQLite
                              severity,          │  ^
                              CWE)               v  │
                                   ownership (OWNERS -> team)   sla (due dates)
                                                       │
            reports (weekly md/html, CSV) <── findings ┴──> API queries, triage, sla-check
```

Contents: 1 Packages and owners · 2 Conventions · 3 Data model · 4 Module
contracts · 5 Ingest pipeline and lifecycle · 6 HTTP API · 7 CLI · 8 Testing.

## 1. Packages and owners

| Package | Responsibility | Owner |
|---|---|---|
| `ledger/core/`, `ledger/migrations/` | settings, database, migrations, clock, logging, errors, models, repository helpers | Jonas Albrecht |
| `ledger/parsers/` | format detection and one parser per scanner format (`pentest_csv.py` written by Ines Duarte, intern 2025) | Priya Raman |
| `ledger/normalize/`, `ledger/dedupe/` | paths, severities, CWE; fingerprints, cross-tool issue keys, baseline, lifecycle, the ingest pipeline | Mateo Rojas |
| `ledger/ownership/`, `ledger/sla/` | OWNERS files, team mapping, SLA policy, business-day calendar, breaches | Samuel Okafor |
| `ledger/api/` | HTTP JSON API | Jonas Albrecht |
| `ledger/cli.py`, `Makefile`, `pyproject.toml`, `scripts/` | command line, CI integration, packaging, benchmarks | Ewa Kowalczyk |
| `ledger/reports/` | weekly reports and CSV export | Samuel Okafor |
| `ledger/seed.py` | deterministic demo database | Ewa Kowalczyk |

Dependencies point one way: `core` imports nothing from Ledger; `parsers`,
`normalize`, `ownership` and `sla` import only `core`; `dedupe` imports those;
`api`, `cli` and `reports` sit on top. No package reaches into another's
private (`_`-prefixed) names.

## 2. Conventions

**Python.** 3.11 and 3.12 are supported (CI runs both). Standard library only
at runtime. No syntax newer than 3.11 (no `type` statements, no PEP 695
generics, no nested same-quote f-strings). `from __future__ import annotations`
at the top of every module.

**Time.** All code gets the current time from `ledger.core.clock.now()`, an
aware UTC `datetime`; never `datetime.now()`, `datetime.utcnow()` or
`time.time()` for business data. Naive datetimes are rejected. The database
stores timestamps as text `YYYY-MM-DDTHH:MM:SSZ` (`clock.isoformat`), which
sorts chronologically; `clock.parse_iso` reads them back. Local time
(`Settings.timezone`, `Europe/Berlin`) is used only for business days and
report weeks. `LEDGER_NOW` freezes the clock for a whole CLI or API process
(demos, reproducible CI reports); entry points call `clock.use(lambda: settings.now)`.

**Settings.** Entry points (`cli.main`, `python3 -m ledger.api`, scripts) call
`config.get_settings()` once and pass the `Settings` object down. Library code
never reads `os.environ` and never calls `get_settings()`.

**Transactions.** Connections are autocommit; every write happens inside
`db.transaction(conn)`. Library functions never begin, commit or roll back:
the caller owns the transaction. The CLI uses one transaction per ingested
file, the API one per request. A nested `transaction()` is a savepoint.
Transactions start with `BEGIN IMMEDIATE`, so concurrent ingests queue on
the busy timeout (5 s) instead of failing on a lock upgrade. One connection
per thread; worker threads open their own with `db.open_db(settings)`.

**Logging.** `log.get_logger("<package>.<module>")`; messages are dotted
event names (`ingest.done`, `api.request`, `sla.breach`), data goes in
`extra={...}`. `log.configure(level, fmt)` is called by entry points only.
Bearer values and `ldg-*` tokens are redacted by the formatters; still, never
log request bodies, tokens or evidence.

**Errors.** Raise subclasses of `ledger.core.errors.LedgerError`; the API turns
`status` and `to_dict()` into the response, the CLI prints `message` and exits
with code 2. Let `sqlite3` errors other than unique violations propagate.

| Class | `code` | `status` | Use |
|---|---|---|---|
| `LedgerError` | `ledger_error` | 500 | base |
| `ConfigError` | `config_error` | 500 | bad settings, unknown time zone |
| `MigrationError` | `migration_error` | 500 | migration file problems |
| `InvalidInput` | `invalid_input` | 400 | bad query/body/CLI value |
| `Unauthorized` | `unauthorized` | 401 | missing or unknown token |
| `Forbidden` | `forbidden` | 403 | read token on an admin endpoint |
| `NotFound` | `not_found` | 404 | unknown id or name |
| `Conflict` | `conflict` | 409 | unique violation (`repo.insert`), duplicate ingest, seed over data |
| `PayloadTooLarge` | `payload_too_large` | 413 | upload above `max_upload_bytes` |
| `ParseError` | `parse_error` | 422 | unreadable report; details `source`, `line` |
| `UnknownFormat` | `unknown_format` | 415 | no parser recognises the content |

Constructor: `LedgerError(message, **details)`; `to_dict()` returns
`{"error": code, "message": message, **details}`.

## 3. Data model

Created by `ledger/migrations/0001_initial.sql` (squashed baseline since 2.0).
New schema changes go in a new file `NNNN_name.sql`; applied files are never
edited (the runner checks checksums).

| Table | Key columns | Notes |
|---|---|---|
| `teams` | `id`, `slug` UNIQUE, `name`, `email` | slug is what OWNERS files and the API use |
| `repos` | `id`, `name` UNIQUE, `full_name`, `url`, `default_branch`, `team_id` | `name` = `checkout-api`; `full_name` = `payments/checkout-api`, changes when a repo moves group; `team_id` is the fallback owner |
| `runs` | `id`, `repo_id`, `branch`, `commit_sha`, `tool`, `source_name`, `source_sha256`, `ingested_at`, `raw_count`, `new_count`, `reopened_count`, `fixed_count` | one row per ingested file; UNIQUE (`repo_id`, `branch`, `commit_sha`, `tool`, `source_sha256`) |
| `findings` | see below | one deduplicated issue per (`repo_id`, `branch`, `fingerprint`) |
| `occurrences` | `finding_id`, `run_id`, `tool`, `rule_id`, `tool_severity`, `tool_fingerprint`, `raw_location`, `message`, `evidence` | every sighting, as the tool reported it (path before normalization) |
| `finding_events` | `finding_id`, `run_id`, `kind`, `from_value`, `to_value`, `actor`, `note`, `created_at` | kinds: `new`, `fixed`, `reopened`, `triage`, `suppressed`, `unsuppressed`, `merged`; `actor` is `ledger` for automatic events, the token name for API triage, `--actor` (default `$USER`) for CLI triage |
| `schema_migrations` | `version`, `name`, `checksum`, `applied_at` | owned by the runner |

`findings` columns: `id`, `repo_id`, `branch`, `tool` (first tool that
reported it), `rule_id`, `fingerprint`, `fingerprint_version` (1),
`issue_key` (cross-tool key, SAST only, else NULL), `message`, `severity`
(`critical|high|medium|low|info`), `tool_severity` (native label), `cwe`
(integer, NULL if unknown), the location (`location_kind`
`code|url|package`, `path`, `line`, `col`, `url`, `parameter`, `package`,
`package_version`), `status` (`new|open|fixed|reopened`), `triage`
(`untriaged|confirmed|false_positive|accepted_risk`), `triage_note`,
`triaged_by`, `triaged_at`, `suppressed` (0/1), `suppression_reason`,
`team_id` (NULL only if the team was deleted), `first_seen_at`,
`last_seen_at`, `fixed_at`, `due_at` (NULL = no SLA), `first_run_id`,
`last_run_id`.

Indexes: `findings (repo_id, branch, issue_key) WHERE issue_key IS NOT NULL`,
`(team_id, status)`, `(status, severity)`, `(last_seen_at)`; `occurrences
(finding_id)`, `(run_id)`; `finding_events (finding_id, created_at)`,
`(created_at)`; `runs (repo_id, branch, tool, ingested_at)`.

"Open" means `status IN ('new', 'open', 'reopened')`
(`models.OPEN_STATUSES`). Reports, team summaries and SLA breaches exclude
suppressed findings and `false_positive` triage unless asked otherwise.

## 4. Module contracts

Signatures below are the public surface of each package. Other packages use
only these.

### 4.1 core

```python
# ledger/core/config.py
ROOT: Path                     # repository root; relative paths resolve against it
DEFAULT_CONFIG: Path           # ROOT / "config/ledger.toml"
@dataclass(frozen=True)
class ApiToken: name: str; role: str  # "read" | "admin"; token: str (not in repr)
@dataclass(frozen=True)
class Settings:
    root: Path; db_path: Path; busy_timeout_ms: int
    api_host: str; api_port: int; max_upload_bytes: int; tokens: tuple[ApiToken, ...]
    log_level: str; log_format: str  # "text" | "json"
    timezone: str; now: datetime | None
    samples_dir: Path; sla_policy_path: Path; holidays_path: Path
def load_settings(path: Path | str | None = None, env: Mapping[str, str] | None = None) -> Settings
def get_settings() -> Settings          # cached load_settings() from os.environ
def set_settings(settings: Settings | None) -> None
```

Environment overrides: `LEDGER_CONFIG`, `LEDGER_DB`, `LEDGER_HOST`,
`LEDGER_PORT`, `LEDGER_LOG_LEVEL`, `LEDGER_LOG_FORMAT`, `LEDGER_TIMEZONE`,
`LEDGER_NOW` (ISO-8601 with offset), `LEDGER_READ_TOKEN` and
`LEDGER_ADMIN_TOKEN` (each replaces all configured tokens of that role with
one token named `env-read` / `env-admin`).

```python
# ledger/core/db.py
def connect(path: Path | str, *, busy_timeout_ms: int = 5000) -> sqlite3.Connection
    # autocommit, row_factory=sqlite3.Row, WAL, foreign_keys=ON, synchronous=NORMAL;
    # creates the parent directory; ":memory:" allowed
def open_db(settings: Settings) -> sqlite3.Connection
@contextmanager
def transaction(conn, *, immediate: bool = True) -> Iterator[sqlite3.Connection]

# ledger/core/migrations.py
MIGRATIONS_DIR: Path           # ledger/migrations
@dataclass(frozen=True)
class Migration: version: int; name: str; path: Path; checksum: str
def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]   # numeric order
def applied(conn) -> dict[int, str]                                  # version -> checksum
def current_version(conn) -> int
def pending(conn, directory: Path = MIGRATIONS_DIR) -> list[Migration]
def migrate(conn, directory: Path = MIGRATIONS_DIR, *, target: int | None = None) -> list[Migration]

# ledger/core/clock.py
UTC
def now() -> datetime
def use(source: Callable[[], datetime] | None) -> None
@contextmanager
def frozen(at: datetime) -> Iterator[FrozenClock]   # FrozenClock.set(at), .advance(**timedelta_kwargs)
def isoformat(value: datetime) -> str               # "2026-09-23T12:00:00Z"
def parse_iso(text: str) -> datetime                # aware UTC; offset required
def zone(name: str) -> ZoneInfo                     # ConfigError if unknown

# ledger/core/log.py
def configure(level: str = "INFO", fmt: str = "text", stream: TextIO | None = None) -> None
def get_logger(name: str) -> logging.Logger         # always under "ledger."
def redact(text: str) -> str
```

```python
# ledger/core/models.py
class Severity(StrEnum): CRITICAL, HIGH, MEDIUM, LOW, INFO     # .rank: 4..0
SEVERITY_ORDER: tuple[Severity, ...]                           # critical first
class Status(StrEnum): NEW, OPEN, FIXED, REOPENED
OPEN_STATUSES: frozenset[Status]                               # new, open, reopened
class Triage(StrEnum): UNTRIAGED, CONFIRMED, FALSE_POSITIVE, ACCEPTED_RISK
class LocationKind(StrEnum): CODE, URL, PACKAGE

@dataclass(frozen=True)
class Location:
    kind: LocationKind
    path: str | None = None; line: int | None = None; column: int | None = None
    url: str | None = None; parameter: str | None = None
    package: str | None = None; version: str | None = None
    @classmethod code(path, line=None, column=None); endpoint(url, parameter=None); dependency(package, version=None)
    def display(self) -> str      # "src/a.py:12:5" | "https://... [param]" | "pkg@1.2.3"

@dataclass(frozen=True)
class RawFinding:
    tool: str; rule_id: str; severity: str  # tool-native label
    location: Location; message: str
    evidence: str | None = None; cwe: int | None = None; tool_fingerprint: str | None = None
    extra: dict[str, str] = {}    # format-specific fields; not part of equality; NOT stored (only evidence, message and raw_location reach the database)

@dataclass(frozen=True)
class ParsedReport: format: str; tool: str; findings: tuple[RawFinding, ...] = (); tool_version: str | None = None

Team(id, slug, name, email)
Repo(id, name, full_name, url, default_branch, team_id)
Run(id, repo_id, branch, commit_sha, tool, source_name, source_sha256, ingested_at,
    raw_count=0, new_count=0, reopened_count=0, fixed_count=0)
Finding(<every findings column, with location as Location, severity/status/triage
        as enums, suppressed as bool, timestamps as datetime>)   # .is_open
FindingEvent(id, finding_id, run_id, kind, from_value, to_value, actor, note, created_at)
IngestResult(run_id, repo, branch, tool, raw_count, new_count=0, reopened_count=0,
             fixed_count=0, unchanged_count=0, merged_count=0, suppressed_count=0)

def as_dict(obj) -> Any     # JSON-ready: nested dataclasses, ISO UTC text, enum values
```

```python
# ledger/core/repo.py  (helpers never commit)
def to_db(value) -> Any                 # datetime -> ISO text, Enum -> value, bool -> int
def placeholders(values) -> str         # "?, ?, ?"; ValueError when empty
def fetch_one(conn, sql, params=()) -> sqlite3.Row | None
def fetch_all(conn, sql, params=()) -> list[sqlite3.Row]
def insert(conn, table, values: Mapping[str, Any]) -> int        # Conflict on UNIQUE
def update(conn, table, row_id, values: Mapping[str, Any]) -> None  # NotFound
def get_row(conn, table, row_id) -> sqlite3.Row                  # NotFound
def get_team(conn, team_id) -> Team;      def team_by_slug(conn, slug) -> Team | None
def get_repo(conn, repo_id) -> Repo;      def repo_by_name(conn, name) -> Repo | None
def get_run(conn, run_id) -> Run;         def run_from_row(row) -> Run
def get_finding(conn, finding_id) -> Finding; def finding_from_row(row) -> Finding
def location_columns(location: Location) -> dict[str, Any]       # Location -> findings columns
def add_event(conn, finding_id, kind, *, run_id=None, from_value=None, to_value=None,
              actor="ledger", note=None) -> int                  # created_at = clock.now()
def finding_events(conn, finding_id) -> list[FindingEvent]        # oldest first
```

Table and column names passed to the helpers must be literals from code; they
are checked against `[a-z_][a-z0-9_]*`. Values always go through parameters.

### 4.2 parsers

```python
# ledger/parsers/registry.py
class Parser(Protocol):
    format: str                                   # "sarif" | "kitewatch" | "depwarden" | "pentest_csv"
    # optional: extensions: tuple[str, ...]       # (".sarif", ".json"); read with getattr, only for tie-breaks
    def sniff(self, data: bytes, filename: str | None) -> bool: ...
    def parse(self, data: bytes, *, source: str) -> ParsedReport: ...
def register(parser: Parser) -> Parser
def formats() -> list[str]
def get_parser(fmt: str) -> Parser                               # UnknownFormat
def detect(data: bytes, filename: str | None = None) -> Parser   # by content; UnknownFormat
def parse_report(data: bytes, *, source: str, fmt: str | None = None) -> ParsedReport
```

Detection looks at the content; the file name only breaks ties: when several
parsers claim a file, those whose `extensions` contain the file's suffix win,
then registration order (`BUILTIN_MODULES`). One file is
one tool: a SARIF file with runs from two different tools is a `ParseError`.
Tool names are lowercase: `brackish`, `thistle` (SAST, SARIF 2.1),
`kitewatch` (DAST, JSON), `depwarden` (dependencies, XML), `pentest`
(manual pentest reports, CSV). Parsers keep what the tool said: native
severity label, path exactly as written, `cwe` only when the report states it.
`source` is the file name used in error messages. Modules: `registry.py`,
`sarif.py`, `kitewatch.py`, `depwarden.py`, `pentest_csv.py`. Format notes
per tool: `docs/parsers.md`.

### 4.3 normalize

```python
# ledger/normalize/paths.py
def normalize_path(raw: str, *, repo: Repo | None = None) -> str
    # repo-relative POSIX path: "\" -> "/", drops file:// and leading "./",
    # strips CI workspace prefixes (/builds/<group>/<repo>/, C:\builds\..., /home/ci/work/<repo>/)
# ledger/normalize/severity.py
SEVERITY_TABLE: dict[str, dict[str, Severity]]       # tool -> native label (lowercase) -> Severity
def normalize_severity(tool: str, native: str) -> Severity   # unknown -> MEDIUM + warning log
# ledger/normalize/cwe.py
def parse_cwe(value: str | int | None) -> int | None        # "CWE-89", "cwe_89", 89 -> 89
# ledger/normalize/finding.py
@dataclass(frozen=True)
class NormalizedFinding: raw: RawFinding; severity: Severity; location: Location; cwe: int | None
def normalize(raw: RawFinding, *, repo: Repo) -> NormalizedFinding
```

### 4.4 dedupe

```python
# ledger/dedupe/fingerprint.py
FINGERPRINT_VERSION = 1
def fingerprint(finding: NormalizedFinding) -> str     # sha256 hex over tool, rule, location fields
# ledger/dedupe/issue_key.py
def issue_key(finding: NormalizedFinding) -> str | None   # SAST code findings with line and CWE
# ledger/dedupe/baseline.py
@dataclass(frozen=True)
class Baseline: entries: tuple[BaselineEntry, ...]
    def match(self, finding: NormalizedFinding) -> BaselineEntry | None
def load_baseline(path: Path) -> Baseline                  # missing file -> empty Baseline
# ledger/dedupe/lifecycle.py
def apply_run(conn, run: Run, findings: Sequence[NormalizedFinding], *, repo: Repo,
              baseline: Baseline, owners: OwnersFile | None, policy: SlaPolicy,
              calendar: BusinessCalendar) -> IngestResult
# ledger/dedupe/ingest.py  (the only entry point the API and CLI use)
BASELINE_FILE = ".ledger-baseline.json"
def baseline_path(settings: Settings, repo: Repo) -> Path   # samples_dir/repos/<name>/.ledger-baseline.json
def ingest_report(conn, settings: Settings, *, repo: Repo, branch: str, commit_sha: str,
                  data: bytes, source: str, fmt: str | None = None) -> IngestResult
```

`IngestResult` counters, per run: `raw_count` sightings in the file;
`new_count` findings inserted; `reopened_count` fixed findings seen again;
`fixed_count` open findings of the run's tool closed because the run did not
report them; `unchanged_count` existing findings seen again without a status
change (including merged ones); `merged_count` distinct existing findings of
the other SAST tool that a sighting was merged into; `suppressed_count`
distinct findings of this run that are suppressed after it (newly or still).
`raw_count`, `new_count`, `reopened_count` and `fixed_count` are also stored on
the `runs` row.

`ingest_report` does not commit (see §5). Raises `ParseError` /
`UnknownFormat` before writing anything, `InvalidInput` for an empty branch or
a commit that is not 7-40 hex characters, `Conflict` when the same file was
already ingested for that repo, branch, commit and tool.

### 4.5 ownership

```python
# ledger/ownership/owners.py
@dataclass(frozen=True)
class OwnerRule: pattern: str; team: str; line: int        # team = slug without "@"
@dataclass(frozen=True)
class OwnersFile:
    rules: tuple[OwnerRule, ...]
    def team_for(self, path: str) -> str | None             # last matching rule wins
def parse_owners(text: str, *, source: str = "OWNERS") -> OwnersFile   # ParseError
def load_owners(path: Path) -> OwnersFile | None            # None when missing
# ledger/ownership/teams.py
def owners_path(settings: Settings, repo: Repo) -> Path     # samples_dir/repos/<name>/OWNERS
def resolve_team_id(conn, repo: Repo, location: Location, owners: OwnersFile | None) -> int
    # code location matched in OWNERS and slug known -> that team; otherwise repo.team_id
```

OWNERS syntax (CODEOWNERS-like): one `<pattern> <owner>` per line, `#`
comments (also trailing). The owner is exactly one team, `@fernwick/<slug>`
or `@<slug>`. `*` matches within a path segment, `?` one character, `**`
across segments, a leading `/` (or any `/` inside the pattern) anchors at the
repo root, a pattern without `/` matches the file name at any depth, a
trailing `/` matches everything below a directory. Any other pattern must
match the whole path: unlike GitHub CODEOWNERS, `/src/auth` does not cover
`src/auth/login.py` (write `/src/auth/`). Baseline `path` globs
(`docs/adr/0003-baseline-file.md`) differ: always anchored at the root, so a
pattern without `/` does not match at any depth. A slug that is not in
`teams` falls back to the repository's team with an `ownership.unknown_team`
warning (logged for every finding, not once per file).

### 4.6 sla

```python
# ledger/sla/calendar.py
@dataclass(frozen=True)
class BusinessCalendar:
    tz: ZoneInfo; holidays: frozenset[date]
    def is_business_day(self, day: date) -> bool
    def add_business_days(self, start: datetime, days: int) -> datetime
        # end (23:59:59 local) of the N-th business day after start's local date, as UTC
    def business_days_between(self, start: datetime, end: datetime) -> int
def load_calendar(path: Path, tz_name: str) -> BusinessCalendar   # config/holidays.toml
# ledger/sla/policy.py
@dataclass(frozen=True)
class SlaPolicy:
    days: Mapping[Severity, int]                             # absent severity = no SLA
    def days_for(self, severity: Severity) -> int | None
def load_policy(path: Path) -> SlaPolicy                     # config/sla.toml
def due_at(severity: Severity, opened_at: datetime, *, policy: SlaPolicy,
           calendar: BusinessCalendar) -> datetime | None
# ledger/sla/breach.py
@dataclass(frozen=True)
class Breach: finding_id: int; repo_id: int; team_id: int | None; severity: Severity
              due_at: datetime; overdue_days: int            # business days
def find_breaches(conn, *, now: datetime, calendar: BusinessCalendar,
                  team_id: int | None = None) -> list[Breach]   # oldest due first
```

Callers build both from the settings: `load_calendar(settings.holidays_path,
settings.timezone)` and `load_policy(settings.sla_policy_path)`; `ingest_report`,
`sla-check`, reports and the teams summary each load them per call.

`config/sla.toml` has a `[days]` table (`critical = 3`, `high = 10`,
`medium = 30`, `low = 60`). `config/holidays.toml` lists
`[[holiday]]` entries with `date` (TOML date) and `name`. Example: a critical
finding first seen Wed 2026-09-23 14:00 Berlin is due Mon 2026-09-28 23:59:59
+02:00 (`2026-09-28T21:59:59Z`).

### 4.7 reports

```python
# ledger/reports/weekly.py
@dataclass(frozen=True)
class TeamWeek: team: Team; opened: int; fixed: int; reopened: int
                open_by_severity: dict[Severity, int]; breaches: tuple[Breach, ...]
                oldest_open: tuple[Finding, ...]             # up to 10
@dataclass(frozen=True)
class WeeklyReport: week_start: date; week_end: date; generated_at: datetime
                    teams: tuple[TeamWeek, ...]
def build_weekly(conn, *, week_start: date, calendar: BusinessCalendar,
                 team_id: int | None = None) -> WeeklyReport  # Monday..Sunday, Europe/Berlin
# ledger/reports/markdown.py
def render_markdown(report: WeeklyReport) -> str
# ledger/reports/html.py
def render_html(report: WeeklyReport) -> str                 # every value html-escaped
# ledger/reports/csv_export.py
def export_findings_csv(conn, out: TextIO, *, team_id: int | None = None,
                        statuses: Sequence[Status] | None = None) -> int   # rows written
```

### 4.8 seed

```python
# ledger/seed.py
ANCHOR = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
def seed_database(conn, *, scale: int = 1, seed: int = 2026, reset: bool = False) -> dict[str, int]
    # counts per table; Conflict when data exists and reset is False; does not commit
```

## 5. Ingest pipeline and lifecycle

`ingest_report` runs inside the caller's transaction:

1. `parsers.registry.parse_report` -> `ParsedReport` (nothing written yet).
2. Insert the `runs` row (`ingested_at = clock.now()`).
3. `normalize.normalize` each `RawFinding`.
4. Baseline from `samples_dir/repos/<repo>/.ledger-baseline.json`
   (`docs/adr/0003-baseline-file.md`); a match marks the finding
   `suppressed` with the entry's reason.
5. `fingerprint` and `issue_key` per finding. SAST findings from two tools
   at the same path, line and CWE share an issue key and merge into the
   existing finding (`docs/adr/0002-cross-tool-dedupe.md`): the occurrence is
   attached to it, a `merged` event is written, no new finding is created.
6. `lifecycle.apply_run`, per repo **and branch**:

| Before | Seen in this run | Not seen in a run of the same tool |
|---|---|---|
| (none) | insert `new`, event `new`, `due_at` from SLA | - |
| `new` / `open` | `open`, refresh `last_seen_at`, `last_run_id` | `fixed`, `fixed_at = now`, event `fixed` |
| `reopened` | stays `reopened`, refresh | `fixed`, event `fixed` |
| `fixed` | `reopened`, `fixed_at = NULL`, `due_at` recomputed from now, event `reopened` | unchanged |

   Only runs of a finding's own `tool` can fix it. A run on another branch
   never touches it. Triage fields are never changed by ingest.
7. Every sighting becomes an `occurrences` row; `team_id` comes from
   `ownership.resolve_team_id`; run counters are updated.

## 6. HTTP API

`python3 -m ledger.api` serves `Settings.api_host:api_port`
(127.0.0.1:8765, `LEDGER_PORT`). JSON in and out, `Authorization: Bearer
<token>`; read tokens may call GET endpoints, admin tokens everything.

| Method and path | Role | Body / query | Response |
|---|---|---|---|
| `GET /api/v1/health` | none | | `{"status": "ok", "version", "schema_version"}` |
| `POST /api/v1/ingest` | admin | raw report bytes; `?repo=&branch=&commit=&format=` | 201 `IngestResult` |
| `GET /api/v1/findings` | read | `repo`, `branch`, `team`, `tool`, `severity`, `status`, `triage` (each repeatable), `suppressed` (`true`/`false`, default `false`), `limit` (default 50, max 200), `offset` | `{"items", "total", "limit", "offset"}`, ordered by severity (critical first) then `id` |
| `GET /api/v1/findings/{id}` | read | | finding plus `occurrences` and `events` |
| `POST /api/v1/findings/{id}/triage` | admin | `{"triage", "note"}` | the finding; event `triage`, actor = token name |
| `GET /api/v1/teams` | read | | per team: open counts by severity, breaches |

A finding is serialized as `models.as_dict(finding)` plus `"repo": <name>`.
The detail adds `occurrences` (every column of the row plus the run's
`commit_sha`, `source_name` and `ingested_at`, oldest first) and `events`
(`as_dict(FindingEvent)`, oldest first). Unknown query parameters, a repeated
single-valued parameter and bad enum values are 400.

**Ingest.** The body is the raw report file, exactly as the scanner wrote it
(no multipart, no JSON wrapper, any `Content-Type`), with a `Content-Length`
of at most `max_upload_bytes` (10 MiB; 413 above, no chunked uploads).
Query: `repo`, `branch`, `commit` (required), `format` (optional, else
detected), `source` (optional original file name, at most 255 characters:
stored as `runs.source_name`, used in error messages and as the detection
tie-break; default `upload`). One transaction per request.

**Teams summary.** `{"items": [...]}`, one item per team ordered by slug:
the `teams` columns (`id`, `slug`, `name`, `email`) plus `open` (counts of
open, unsuppressed, non-false-positive findings per severity, all five keys
present), `open_total` and `breaches` (the number of `find_breaches` results
for the team at `clock.now()`, so it always agrees with `ledger sla-check`).

Errors are `LedgerError.to_dict()` with its status; unknown routes 404
(before authentication), wrong method 405 with an `Allow` header
(`MethodNotAllowed`, code `method_not_allowed`, is defined in
`ledger/api/router.py`, not in `core.errors`: only the router raises it),
missing or unknown token 401 with `WWW-Authenticate`, read token on an admin
route 403, unexpected exceptions a generic 500 (logged as `api.error`).

## 7. CLI

`python3 -m ledger <command>` (or `ledger` once installed); entry point
`ledger.cli.main(argv: Sequence[str] | None = None) -> int`.

| Command | Notes |
|---|---|
| `migrate` | apply pending migrations |
| `seed [--reset] [--scale N] [--seed N]` | demo data; one transaction |
| `ingest --repo NAME --branch B --commit SHA [--format F] FILE...` | one transaction per file; a failed file does not undo the others; exit 1 if any failed |
| `ingest --manifest samples/manifest.json` | files, repos, branches and commits from the manifest, in order |
| `findings [--repo] [--team] [--severity] [--status] [--limit N] [--json]` | |
| `triage ID --set {confirmed,false_positive,accepted_risk,untriaged} [--note] [--actor]` | |
| `report --week YYYY-MM-DD [--team SLUG] --format {md,html,csv} [--out PATH]` | |
| `sla-check [--team SLUG] [--json]` | exit 1 when breaches exist (CI gate) |

`findings` filters are repeatable (OR within a flag, AND across flags) and
literal: `--status open` matches only `open`, not `new` or `reopened`.
Suppressed findings are never listed by the CLI (the API has
`suppressed=true`). `report --week` must be a Monday (argparse rejects other
days; `build_weekly` itself moves any date back to its Monday); `--format csv`
exports every unsuppressed, non-false-positive finding and ignores `--week`.
Every command except `migrate` refuses to run while migrations are pending.

**Manifest** (`samples/manifest.json`): a JSON list of runs, or an object
with a `runs` list (other top-level keys such as `description` are ignored).
Each run needs string `file` (relative to the manifest's directory), `repo`,
`branch` and `commit`; `format` is optional (detected otherwise); other keys
(`tool`, `note` in the samples) are documentation only. Runs are ingested in
list order, one transaction each, and the repository must exist.

```json
{"description": "...", "runs": [
  {"file": "brackish/checkout-api/brackish-2026-08-24-6ffbc65.sarif", "repo": "checkout-api",
   "branch": "main", "commit": "6ffbc65cdbb1a9074894068dcafc7cd6e6ae854a", "tool": "brackish", "note": "..."}]}
```

Exit codes: 0 ok, 1 command-level failure (breaches, a failed file), 2
`LedgerError` / usage error.

## 8. Testing

`make test` = `python3 -m unittest discover -s tests -t .`; narrow with
`make test TESTS=tests/dedupe`. Tests live in `tests/<package>/`. Shared
fixtures in `tests/helpers.py`:

* `LedgerTestCase`: a fresh migrated SQLite file in a temporary directory
  (`self.conn`, `self.settings`, `self.tmp`) and the clock frozen at `TODAY`
  (`self.clock`, a `FrozenClock`). Nothing touches `var/` or the real
  environment, so test modules can run in parallel processes.
* `TODAY` = 2026-09-23 12:00 UTC (14:00 in Leipzig).
* `make_settings(directory, **overrides)` builds settings from the checked-in
  config without reading `os.environ`.
* `tests/integration/test_pipeline.py` runs the whole chain with nothing
  faked: seed, the demo manifest through `ingest_report`, `sla-check`, the
  HTTP API and a weekly report. Unit suites of `dedupe` swap parsers,
  ownership and SLA for stand-ins (`tests/dedupe/fakes.py`) to test dedupe's
  own rules.
* Factories (insert and return the model): `make_team(conn, slug=None)`,
  `make_repo(conn, name=None, *, team=None)`, `make_run(conn, repo=None,
  **fields)`, `make_finding(conn, run=None, *, location=None, **fields)`,
  `raw_finding(**fields)` (a Brackish SQL injection `RawFinding`) and
  `sarif_report((path, line), ...)` (a minimal SARIF log as bytes).
