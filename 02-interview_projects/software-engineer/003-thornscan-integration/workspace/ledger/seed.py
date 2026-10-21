"""Deterministic demo database: 8 teams, 14 repositories, ~3,000 findings over 10 weeks.

Simulates weekly CI scans ending at ``ANCHOR`` (world "today", not the wall
clock); the same ``seed`` and ``scale`` give the same rows, ids and timestamps.
``scale`` multiplies the findings (17 is about 51,000) while runs stay the same.
The caller owns the transaction; outside one every insert commits on its own.
"""

from __future__ import annotations

import hashlib
import random
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from ledger.core.clock import UTC, isoformat
from ledger.core.errors import Conflict
from ledger.core.models import SEVERITY_ORDER, Severity

ANCHOR = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
WEEKS = 10
FINDINGS_PER_SCALE = 3000
TABLES = ("teams", "repos", "runs", "findings", "occurrences", "finding_events")

TEAMS = (
    ("payments", "Payments"), ("routing", "Routing"), ("fleet", "Fleet"), ("warehouse", "Warehouse"),
    ("customs", "Customs"), ("identity", "Identity"), ("platform", "Platform"), ("tracking", "Tracking"),
)  # fmt: skip
# name, team id, language, share of findings, tools. wms-core is the legacy monolith that skews Warehouse.
REPOS = (
    ("checkout-api", 1, "py", 4, ("brackish", "thistle", "kitewatch", "depwarden", "pentest")),
    ("payouts-worker", 1, "py", 11, ("brackish", "depwarden")),
    ("route-planner", 2, "py", 3, ("brackish", "thistle", "kitewatch", "depwarden")),
    ("eta-service", 2, "go", 9, ("thistle", "kitewatch", "depwarden")),
    ("fleet-telemetry", 3, "go", 6, ("thistle", "depwarden")),
    ("driver-app", 3, "kt", 7, ("brackish", "depwarden")),
    ("wms-core", 4, "java", 22, ("brackish", "thistle", "kitewatch", "depwarden")),
    ("slotting-engine", 4, "java", 5, ("brackish", "depwarden")),
    ("customs-docs", 5, "ts", 6, ("thistle", "kitewatch", "depwarden")),
    ("auth-gateway", 6, "go", 5, ("brackish", "thistle", "kitewatch", "depwarden", "pentest")),
    ("sso-admin", 6, "ts", 4, ("thistle", "kitewatch", "depwarden")),
    ("build-images", 7, "py", 3, ("depwarden",)),
    ("tracking-portal", 8, "ts", 6, ("thistle", "kitewatch", "depwarden", "pentest")),
    ("shipment-events", 8, "java", 4, ("brackish", "depwarden")),
)
SOURCE_ROOTS = {"route-planner": "planner", "checkout-api": "src/checkout"}
RELEASE_BRANCHES = {"checkout-api": "release/2026.09", "route-planner": "release/3.4", "wms-core": "release/5.12"}
# `make demo` ingests samples/ into these repos' main branch; the seed keeps to their release branch (week 6 on).
DEMO_REPOS = {"checkout-api", "route-planner"}
PENTEST_WEEKS = (0, 8)  # Harrowgate test in July, retest in September
PENTEST_PREFIX = {"auth-gateway": "AGW", "tracking-portal": "TRK"}
KITEWATCH_V2 = {"checkout-api", "wms-core", "customs-docs"}  # still on Kitewatch 2.9 (numeric risk 1-5)
TOOL_WEIGHT = {"brackish": 30, "thistle": 25, "kitewatch": 12, "depwarden": 30, "pentest": 3}
# critical, high, medium, low, info. SARIF levels stop at "error" (high): SAST never reports critical.
SEVERITY_WEIGHTS = {
    "brackish": (0, 16, 46, 30, 8), "thistle": (0, 14, 44, 34, 8), "kitewatch": (1, 9, 35, 35, 20),
    "depwarden": (6, 24, 42, 24, 4), "pentest": (8, 25, 40, 20, 7),
}  # fmt: skip
# Native labels as the tools write them (tool_severity), matching normalize.severity.
NATIVE = {
    "brackish": ("error", "error", "warning", "note", "none"),
    "thistle": ("error", "error", "warning", "note", "none"),
    "kitewatch": ("Critical", "High", "Medium", "Low", "Info"),
    "kitewatch-v2": ("5", "4", "3", "2", "1"),
    "depwarden": ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"),
    "pentest": ("Critical", "High", "Medium", "Low", "Informational"),
}
FIX_RATE = {Severity.CRITICAL: 0.85, Severity.HIGH: 0.7, Severity.MEDIUM: 0.4, Severity.LOW: 0.25, Severity.INFO: 0.15}
# Brackish rule, Thistle rule, CWE, severities (h, m, l, i), message. Same CWE: the two merge by issue key.
SAST_RULES = (
    ("BRK-SQLI-001", "TH-INJ-SQL", 89, "h", "SQL query built from request data"),
    ("BRK-XSS-002", "TH-XSS-TEMPLATE", 79, "hm", "Unescaped user input rendered in HTML response"),
    ("BRK-HASH-003", "TH-CRYPTO-HASH", 328, "ml", "Weak hash algorithm (MD5) used for a token"),
    ("BRK-SECRET-004", "TH-SECRET-LITERAL", 798, "h", "Hard-coded credential in source"),
    ("BRK-SSRF-005", "TH-NET-SSRF", 918, "hm", "Outbound request to a URL taken from user input"),
    ("BRK-PATH-006", "TH-PATH-TRAVERSAL", 22, "hm", "File path built from request parameter"),
    ("BRK-XXE-007", "TH-XML-XXE", 611, "hm", "XML parser resolves external entities"),
    ("BRK-DESER-008", "TH-DESER-UNSAFE", 502, "h", "Untrusted data deserialized"),
    ("BRK-ASSERT-009", "TH-ASSERT-CHECK", 617, "li", "assert used for an access check"),
    ("BRK-CMDI-010", "TH-INJ-CMD", 78, "h", "Shell command built from user input"),
    ("BRK-REDOS-011", "TH-REGEX-REDOS", 1333, "ml", "Regular expression with catastrophic backtracking"),
    ("BRK-LOG-012", "TH-LOG-INJECT", 117, "mli", "Unsanitized input written to the log"),
    ("BRK-RAND-013", "TH-RAND-INSECURE", 330, "ml", "Non-cryptographic random used for a token"),
    ("BRK-REDIRECT-014", "TH-REDIRECT-OPEN", 601, "ml", "Redirect target taken from the query string"),
    ("BRK-DEBUG-015", "TH-CONF-DEBUG", 489, "li", "Debug mode enabled in production settings"),
)
# rule, CWE, severities, message, has a parameter. Pentest ids are HG-<repo prefix>-<nn> (Harrowgate).
KITEWATCH_RULES = (
    ("KW-SQLI-001", 89, "ch", "SQL injection (error based)", True),
    ("KW-XSS-002", 79, "chm", "Reflected cross-site scripting", True),
    ("KW-COOKIE-003", 614, "ml", "Cookie without Secure flag", False),
    ("KW-HDR-004", 319, "li", "Strict-Transport-Security header missing", False),
    ("KW-INFO-005", 200, "li", "Server version disclosed", False),
    ("KW-CORS-006", 942, "hm", "CORS policy allows any origin with credentials", False),
    ("KW-REDIRECT-007", 601, "ml", "Open redirect", True),
    ("KW-FRAME-008", 1021, "ml", "Missing anti-clickjacking header", False),
    ("KW-ERR-009", 209, "mli", "Stack trace in error response", True),
)
PENTEST_RULES = (
    ("01", 639, "chm", "Records of another customer readable by changing the id (IDOR)", True),
    ("02", 347, "ch", "JWT accepted with alg none", False),
    ("03", 307, "hm", "No rate limiting on login", False),
    ("04", 79, "hm", "Stored XSS in delivery address field", True),
    ("05", 640, "ml", "Password reset token valid for 7 days", False),
    ("06", 209, "li", "Stack traces in API error responses", False),
)
PACKAGES = {
    "py": ("fastjwt", "flask-lite", "geojsonkit", "invoicegen", "lxml-lite", "msgcache", "pillowcase", "requestor",
           "tilecache", "yamlette"),
    "go": ("netlite", "cryptokit-go", "yamlgo", "jwtgo", "grpc-lite", "geohashgo"),
    "java": ("logbook-core", "jsonbind", "snakeskin-yaml", "textkit-commons", "nettle-http", "springlet-web"),
    "kt": ("httpkit-android", "gsonette", "iokit-commons", "snakeskin-yaml"),
    "ts": ("fetchly", "args-mini", "jwt-simple-ts", "expresslet", "semverish", "wsocket", "datefmt"),
}  # fmt: skip
DEP_ISSUES = (
    (400, "uncontrolled resource consumption"), (502, "unsafe deserialization"), (1321, "prototype pollution"),
    (22, "path traversal in archive extraction"), (79, "cross-site scripting in error page"),
    (918, "server-side request forgery via redirect"), (347, "signature check can be skipped"),
)  # fmt: skip
_SAST_PAIR = {a: b for brackish, thistle, *_ in SAST_RULES for a, b in ((brackish, thistle), (thistle, brackish))}
AREAS = ("api", "db", "services", "jobs", "auth", "util", "web", "integrations")
MODULES = ("handlers", "models", "queries", "views", "client", "tasks", "serializers", "config", "export", "webhooks")
RESOURCES = ("orders", "shipments", "routes", "drivers", "invoices", "users", "documents", "stops", "slots", "events")
ACTIONS = ("", "/search", "/{id}", "/{id}/status", "/export", "/bulk")
PARAMS = ("q", "id", "sort", "redirect", "filter", "page", "callback", "lang")
TRIAGE_NOTES = {
    "confirmed": ("fix planned this sprint", "ticket created in team backlog", None),
    "false_positive": ("input is an enum validated upstream", "test-only code path", "scanner misreads the ORM call"),
    "accepted_risk": ("compensating WAF rule, see SEC-311", "service retired in Q4", "internal network only, SEC-298"),
}
SUPPRESSION_REASONS = ("test fixture, not deployed", "vendored code, tracked upstream", "generated client code")
ACTORS, TEAM_ACTORS = ("appsec-admin", "sokafor", "praman", "mrojas"), {1: "hsato", 2: "lmoreau"}


def seed_database(
    conn: sqlite3.Connection, *, scale: int = 1, seed: int = 2026, reset: bool = False,
    policy: Any = None, calendar: Any = None,
) -> dict[str, int]:  # fmt: skip
    """Load the demo data; returns row counts per table. Does not commit.

    ``policy`` and ``calendar`` default to the checked-in ``config/sla.toml``
    and ``config/holidays.toml`` (Europe/Berlin).
    """
    if scale < 1:
        raise ValueError("scale must be at least 1")
    if reset:
        for table in reversed(TABLES):
            conn.execute(f"DELETE FROM {table}")
    elif any(conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in TABLES):
        raise Conflict("database already has data; seed with --reset to replace it")
    if policy is None or calendar is None:
        from ledger.core.config import DEFAULT_CONFIG, load_settings
        from ledger.sla.calendar import load_calendar
        from ledger.sla.policy import load_policy

        settings = load_settings(DEFAULT_CONFIG, env={})
        policy = policy or load_policy(settings.sla_policy_path)
        calendar = calendar or load_calendar(settings.holidays_path, settings.timezone)
    data = _Simulation(random.Random(seed), policy, calendar).run(FINDINGS_PER_SCALE * scale)
    for table in TABLES:
        rows = data[table]
        conn.executemany(f"INSERT INTO {table} ({', '.join(rows[0])}) VALUES ({', '.join('?' * len(rows[0]))})",
                         [tuple(row.values()) for row in rows])  # fmt: skip
    return {table: len(data[table]) for table in TABLES}


class _Simulation:
    def __init__(self, rng: random.Random, policy: Any, calendar: Any) -> None:
        self.rng, self.policy, self.calendar = rng, policy, calendar
        self.rows: dict[str, list[dict[str, Any]]] = {table: [] for table in TABLES}
        self.schedule: dict[tuple[int, str, str], list[tuple[int, datetime]]] = {}
        self.run_stats: dict[int, Counter[str]] = {}
        self.due_cache: dict[tuple[int, Any], datetime] = {}
        self.taken: set[tuple[int, str, str]] = set()

    def run(self, count: int) -> dict[str, list[dict[str, Any]]]:
        self.rows["teams"] = [{"id": team_id, "slug": slug, "name": name, "email": f"{slug}-team@fernwick.example.test"}
                              for team_id, (slug, name) in enumerate(TEAMS, 1)]  # fmt: skip
        for repo_id, (name, team_id, *_) in enumerate(REPOS, 1):
            full_name = f"{TEAMS[team_id - 1][0]}/{name}"
            url = f"https://git.fernwick.example.test/{full_name}"
            self.rows["repos"].append({"id": repo_id, "name": name, "full_name": full_name, "url": url,
                                       "default_branch": "main", "team_id": team_id})  # fmt: skip
        self._runs()
        weights = [spec[3] for spec in REPOS]
        for finding_id in range(1, count + 1):
            self._finding(finding_id, self.rng.choices(range(1, len(REPOS) + 1), weights=weights)[0])
        for run in self.rows["runs"]:
            run.update({f"{key}_count": self.run_stats[run["id"]][key] for key in ("raw", "new", "reopened", "fixed")})
        return self.rows

    def _runs(self) -> None:
        planned = []
        for repo_id, (name, _team, _lang, _w, tools) in enumerate(REPOS, 1):
            branches = [] if name in DEMO_REPOS else [("main", range(WEEKS))]
            if name in RELEASE_BRANCHES:
                branches.append((RELEASE_BRANCHES[name], range(6, WEEKS)))
            for branch, weeks in branches:
                commits = {w: f"{self.rng.getrandbits(160):040x}" for w in weeks}
                for tool in (t for t in tools if branch == "main" or t != "pentest"):
                    offset = timedelta(hours=self.rng.randint(2, 60), minutes=self.rng.randint(0, 59))
                    for week in PENTEST_WEEKS if tool == "pentest" else weeks:
                        at = ANCHOR - timedelta(weeks=WEEKS - 1 - week) - offset
                        planned.append((at, repo_id, branch, tool, commits[week]))
        ext = {"brackish": "sarif", "thistle": "sarif", "kitewatch": "json", "depwarden": "xml", "pentest": "csv"}
        for run_id, (at, repo_id, branch, tool, commit) in enumerate(sorted(planned), 1):
            self.rows["runs"].append({
                "id": run_id, "repo_id": repo_id, "branch": branch, "commit_sha": commit, "tool": tool,
                "source_name": f"{tool}-{REPOS[repo_id - 1][0]}-{commit[:8]}.{ext[tool]}",
                "source_sha256": f"{self.rng.getrandbits(256):064x}", "ingested_at": isoformat(at),
            })  # fmt: skip
            self.schedule.setdefault((repo_id, branch, tool), []).append((run_id, at))
            self.run_stats[run_id] = Counter()

    def _finding(self, finding_id: int, repo_id: int) -> None:
        rng = self.rng
        name, team_id, lang, _weight, tools = REPOS[repo_id - 1]
        release = name in DEMO_REPOS or (name in RELEASE_BRANCHES and rng.random() < 0.1)
        branch = RELEASE_BRANCHES[name] if release else "main"
        tools = [t for t in tools if (repo_id, branch, t) in self.schedule]  # no pentest on release branches
        tool = rng.choices(tools, weights=[TOOL_WEIGHT[t] for t in tools])[0]
        runs = self.schedule[(repo_id, branch, tool)]
        severity = rng.choices(SEVERITY_ORDER, weights=SEVERITY_WEIGHTS[tool])[0]
        while True:
            rule_id, cwe, message, location, evidence = self._what(tool, name, lang, severity)
            fingerprint = _fingerprint(tool, rule_id, location)
            if (repo_id, branch, fingerprint) not in self.taken:
                self.taken.add((repo_id, branch, fingerprint))
                break

        first = 0 if rng.random() < 0.35 else rng.randrange(len(runs))  # a third is the first-scan backlog
        seen, fixed, reopened = list(range(first, len(runs))), None, None
        if first < len(runs) - 1 and rng.random() < FIX_RATE[severity]:
            fixed = rng.randrange(first + 1, len(runs))
            seen = list(range(first, fixed))
            if fixed < len(runs) - 1 and rng.random() < 0.08:
                reopened = rng.randrange(fixed + 1, len(runs))
                seen += range(reopened, len(runs))
        first_run, first_at = runs[first]
        last_run, last_at = runs[seen[-1]]
        if reopened is not None:
            status, opened_at = "reopened", runs[reopened][1]
        elif fixed is not None:
            status, opened_at = "fixed", first_at
        else:
            status, opened_at = ("new" if first == len(runs) - 1 else "open"), first_at
        suppressed = tool != "pentest" and rng.random() < 0.03
        triage, note, triaged_by, triaged_at = self._triage(team_id, first_at)
        issue_key = None
        if tool in ("brackish", "thistle"):
            issue_key = f"{location['path']}:{location['line']}:CWE-{cwe}"  # as dedupe.issue_key
        self.rows["findings"].append({
            "id": finding_id, "repo_id": repo_id, "branch": branch, "tool": tool, "rule_id": rule_id,
            "fingerprint": fingerprint, "fingerprint_version": 1, "issue_key": issue_key, "message": message,
            "severity": severity.value, "tool_severity": _native(tool, severity, name), "cwe": cwe, **location,
            "status": status, "triage": triage, "triage_note": note, "triaged_by": triaged_by,
            "triaged_at": triaged_at and isoformat(triaged_at), "suppressed": int(suppressed),
            "suppression_reason": rng.choice(SUPPRESSION_REASONS) if suppressed else None, "team_id": team_id,
            "first_seen_at": isoformat(first_at), "last_seen_at": isoformat(last_at),
            "fixed_at": isoformat(runs[fixed][1]) if status == "fixed" else None,
            "due_at": self._due(severity, opened_at), "first_run_id": first_run, "last_run_id": last_run,
        })  # fmt: skip

        raw = _raw_location(tool, TEAMS[team_id - 1][0], name, location)
        for index in seen:
            self._occurrence(finding_id, runs[index][0], tool, rule_id, _native(tool, severity, name), raw, message,
                             evidence)  # fmt: skip
        self._event(finding_id, "new", first_run, first_at, to_value="new")
        self.run_stats[first_run]["new"] += 1
        if fixed is not None:
            self._event(finding_id, "fixed", runs[fixed][0], runs[fixed][1], from_value="open", to_value="fixed")
            self.run_stats[runs[fixed][0]]["fixed"] += 1
        if reopened is not None:
            self._event(finding_id, "reopened", runs[reopened][0], runs[reopened][1], from_value="fixed",
                        to_value="reopened")  # fmt: skip
            self.run_stats[runs[reopened][0]]["reopened"] += 1
        if suppressed:
            self._event(finding_id, "suppressed", first_run, first_at, to_value="baseline")
        if triage != "untriaged":
            self._event(finding_id, "triage", None, triaged_at, from_value="untriaged", to_value=triage,
                        actor=triaged_by, note=note)  # fmt: skip
        other = {"brackish": "thistle", "thistle": "brackish"}.get(tool)
        if other in tools and rng.random() < 0.12:  # the other SAST tool reports it too: merged by issue key
            other_runs = self.schedule[(repo_id, branch, other)]
            later = [other_runs[index] for index in seen if other_runs[index][1] > first_at]
            other_rule = _SAST_PAIR[rule_id]
            other_raw = _raw_location(other, TEAMS[team_id - 1][0], name, location)
            for run_id, _at in later:
                self._occurrence(finding_id, run_id, other, other_rule, _native(other, severity, name), other_raw,
                                 message, None)  # fmt: skip
            if later:
                self._event(finding_id, "merged", later[0][0], later[0][1], from_value=other,
                            note=f"{other_rule}: same path, line and CWE")  # fmt: skip

    def _what(self, tool: str, repo_name: str, lang: str, severity: Severity) -> tuple[Any, ...]:
        rng, letter = self.rng, severity.value[0]
        if tool in ("brackish", "thistle"):
            brackish, thistle, cwe, _sev, message = rng.choice([r for r in SAST_RULES if letter in r[3]])
            area, module = rng.choice(AREAS), rng.choice(MODULES)
            pkg = repo_name.split("-")[0]
            path = {
                "py": f"{SOURCE_ROOTS.get(repo_name, 'src/' + pkg)}/{area}/{module}.py",
                "go": f"internal/{area}/{module}.go",
                "ts": f"src/{area}/{module}.ts",
                "java": f"src/main/java/net/fernwick/{pkg}/{area}/{module.title()}.java",
                "kt": f"app/src/main/kotlin/net/fernwick/{pkg}/{area}/{module.title()}.kt",
            }[lang]  # fmt: skip
            location = _columns("code", path=path, line=rng.randint(5, 900), col=rng.randint(1, 60))
            return brackish if tool == "brackish" else thistle, cwe, message, location, None
        if tool == "depwarden":
            package, (cwe, issue) = rng.choice(PACKAGES[lang]), rng.choice(DEP_ISSUES)
            version = f"{rng.randint(0, 5)}.{rng.randint(0, 20)}.{rng.randint(0, 12)}"
            rule_id = f"DWA-{rng.randint(2023, 2026)}-{rng.randint(1, 1999):04d}"
            location = _columns("package", package=package, package_version=version)
            return rule_id, cwe, f"{package} {version}: {issue}", location, f"{repo_name} > {package} {version}"
        rules = KITEWATCH_RULES if tool == "kitewatch" else PENTEST_RULES
        rule_id, cwe, _sev, message, has_param = rng.choice([r for r in rules if letter in r[2]])
        if tool == "pentest":
            rule_id = f"HG-{PENTEST_PREFIX[repo_name]}-{rule_id}"
        url = f"https://{repo_name}.staging.fernwick.example.test/api/v{rng.randint(1, 2)}/{rng.choice(RESOURCES)}"
        url += rng.choice(ACTIONS).replace("{id}", str(rng.randint(100, 99999)))
        parameter = rng.choice(PARAMS) if has_param else None
        query = f"?{parameter}=%27%22%3E" if parameter else ""
        evidence = f"{rng.choice(('GET', 'POST'))} {url}{query} -> HTTP {rng.choice((200, 500))}"
        return rule_id, cwe, message, _columns("url", url=url, parameter=parameter), evidence

    def _triage(self, team_id: int, first_at: datetime) -> tuple[str, str | None, str | None, datetime | None]:
        rng = self.rng
        age = ANCHOR - first_at
        weights = (66, 18, 5, 15 if team_id == 1 else 7)  # Payments accepts risk more often (docs/requests/)
        triage = rng.choices(("untriaged", "confirmed", "false_positive", "accepted_risk"), weights=weights)[0]
        if triage == "untriaged" or age < timedelta(days=1):
            return "untriaged", None, None, None
        actor = rng.choice((*ACTORS, TEAM_ACTORS.get(team_id, ACTORS[0])))
        at = first_at + timedelta(seconds=rng.randint(3600, int(min(age, timedelta(days=14)).total_seconds())))
        return triage, rng.choice(TRIAGE_NOTES[triage]), actor, at.replace(microsecond=0)

    def _due(self, severity: Severity, opened_at: datetime) -> str | None:
        days = self.policy.days_for(severity)
        if days is None:
            return None
        key = (days, opened_at.astimezone(self.calendar.tz).date())
        if key not in self.due_cache:  # due depends only on the local day; spares 50k calendar walks
            self.due_cache[key] = self.calendar.add_business_days(opened_at, days)
        return isoformat(self.due_cache[key])

    def _occurrence(self, finding_id: int, run_id: int, tool: str, rule_id: str, native: str,
                    raw: str, message: str, evidence: str | None) -> None:  # fmt: skip
        self.rows["occurrences"].append({
            "id": len(self.rows["occurrences"]) + 1, "finding_id": finding_id, "run_id": run_id, "tool": tool,
            "rule_id": rule_id, "tool_severity": native, "tool_fingerprint": None,
            "raw_location": raw, "message": message, "evidence": evidence,
        })  # fmt: skip
        self.run_stats[run_id]["raw"] += 1

    def _event(self, finding_id: int, kind: str, run_id: int | None, at: datetime, *, from_value: str | None = None,
               to_value: str | None = None, actor: str = "ledger", note: str | None = None) -> None:  # fmt: skip
        self.rows["finding_events"].append({
            "id": len(self.rows["finding_events"]) + 1, "finding_id": finding_id, "run_id": run_id, "kind": kind,
            "from_value": from_value, "to_value": to_value, "actor": actor, "note": note, "created_at": isoformat(at),
        })  # fmt: skip


def _columns(kind: str, **values: Any) -> dict[str, Any]:
    columns = dict.fromkeys(("path", "line", "col", "url", "parameter", "package", "package_version"))
    return {"location_kind": kind, **columns, **values}


def _fingerprint(tool: str, rule_id: str, location: dict[str, Any]) -> str:
    """The fields of ``dedupe.fingerprint`` v1, so re-ingesting a seeded issue matches its finding."""
    kind = location["location_kind"]
    place = {"code": ("path", "line"), "url": ("url", "parameter"), "package": ("package",)}[kind]
    fields = ["v1", tool, rule_id, kind, *(location[name] for name in place)]
    return hashlib.sha256("\x1f".join("" if v is None else str(v) for v in fields).encode()).hexdigest()


def _native(tool: str, severity: Severity, repo_name: str) -> str:
    table = "kitewatch-v2" if tool == "kitewatch" and repo_name in KITEWATCH_V2 else tool
    return NATIVE[table][SEVERITY_ORDER.index(severity)]


def _raw_location(tool: str, team_slug: str, repo_name: str, location: dict[str, Any]) -> str:
    """``Location.display()`` before normalization: Thistle reports absolute CI workspace URIs."""
    if location["location_kind"] == "code":
        prefix = f"file:///builds/{team_slug}/{repo_name}/" if tool == "thistle" else ""
        return f"{prefix}{location['path']}:{location['line']}:{location['col']}"
    if location["location_kind"] == "url":
        return f"{location['url']} [{location['parameter']}]" if location["parameter"] else location["url"]
    return f"{location['package']}@{location['package_version']}"
