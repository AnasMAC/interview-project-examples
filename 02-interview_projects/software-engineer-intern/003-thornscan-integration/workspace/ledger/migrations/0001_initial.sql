-- 0001_initial: Ledger data model (squashed at 2.0.0; earlier history in CHANGELOG).
-- Timestamps are TEXT 'YYYY-MM-DDTHH:MM:SSZ' (UTC). Booleans are INTEGER 0/1.

CREATE TABLE teams (
    id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);

CREATE TABLE repos (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,                  -- 'checkout-api'
    full_name TEXT NOT NULL,                    -- 'payments/checkout-api' (changes when a repo moves)
    url TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    team_id INTEGER NOT NULL REFERENCES teams(id)
);

-- One ingested report file.
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    branch TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    tool TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    raw_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    reopened_count INTEGER NOT NULL DEFAULT 0,
    fixed_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (repo_id, branch, commit_sha, tool, source_sha256)
);
CREATE INDEX ix_runs_repo_branch_tool ON runs (repo_id, branch, tool, ingested_at);

-- One deduplicated issue per repo + branch.
CREATE TABLE findings (
    id INTEGER PRIMARY KEY,
    repo_id INTEGER NOT NULL REFERENCES repos(id),
    branch TEXT NOT NULL,
    tool TEXT NOT NULL,                         -- first tool that reported it
    rule_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    fingerprint_version INTEGER NOT NULL DEFAULT 1,
    issue_key TEXT,                             -- cross-tool key (SAST only)
    message TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    tool_severity TEXT NOT NULL,
    cwe INTEGER,
    location_kind TEXT NOT NULL CHECK (location_kind IN ('code', 'url', 'package')),
    path TEXT,
    line INTEGER,
    col INTEGER,
    url TEXT,
    parameter TEXT,
    package TEXT,
    package_version TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'open', 'fixed', 'reopened')),
    triage TEXT NOT NULL DEFAULT 'untriaged'
        CHECK (triage IN ('untriaged', 'confirmed', 'false_positive', 'accepted_risk')),
    triage_note TEXT,
    triaged_by TEXT,
    triaged_at TEXT,
    suppressed INTEGER NOT NULL DEFAULT 0 CHECK (suppressed IN (0, 1)),
    suppression_reason TEXT,
    team_id INTEGER REFERENCES teams(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    fixed_at TEXT,
    due_at TEXT,
    first_run_id INTEGER NOT NULL REFERENCES runs(id),
    last_run_id INTEGER NOT NULL REFERENCES runs(id),
    UNIQUE (repo_id, branch, fingerprint)
);
CREATE INDEX ix_findings_issue_key ON findings (repo_id, branch, issue_key) WHERE issue_key IS NOT NULL;
CREATE INDEX ix_findings_team_status ON findings (team_id, status);
CREATE INDEX ix_findings_status_severity ON findings (status, severity);
CREATE INDEX ix_findings_last_seen ON findings (last_seen_at);

-- Every sighting of a finding in a run, as the tool reported it.
CREATE TABLE occurrences (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    tool TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    tool_severity TEXT NOT NULL,
    tool_fingerprint TEXT,
    raw_location TEXT NOT NULL,                 -- Location.display() before normalization
    message TEXT NOT NULL,
    evidence TEXT
);
CREATE INDEX ix_occurrences_finding ON occurrences (finding_id);
CREATE INDEX ix_occurrences_run ON occurrences (run_id);

-- Lifecycle and triage history. kind: new, fixed, reopened, triage, suppressed, unsuppressed, merged.
CREATE TABLE finding_events (
    id INTEGER PRIMARY KEY,
    finding_id INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    run_id INTEGER REFERENCES runs(id),
    kind TEXT NOT NULL,
    from_value TEXT,
    to_value TEXT,
    actor TEXT NOT NULL DEFAULT 'ledger',
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX ix_finding_events_finding ON finding_events (finding_id, created_at);
CREATE INDEX ix_finding_events_created ON finding_events (created_at);
