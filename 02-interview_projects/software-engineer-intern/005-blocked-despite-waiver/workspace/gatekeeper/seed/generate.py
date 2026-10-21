"""Deterministic demo data (docs/architecture.md, "Seeded data contract").

Rows are built in memory and bulk-inserted straight into the tables with
explicit ids; sequences are moved past them at the end. The decisions are
produced by a small stand-in for the evaluator (same reason format) so the
seed does not depend on the evaluation package. Everything derives from one
``random.Random(seed)``: the same seed and scale give the same database.
"""

from __future__ import annotations

import bisect
import fnmatch
import hashlib
import operator
import random
import re
import zlib
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import Connection, Table, func, insert, select, text, update

from gatekeeper.core import tables
from gatekeeper.core.auth import ROLE_REVIEWER, ROLE_TEAM, issue_key
from gatekeeper.core.contracts import SEVERITIES, severity_rank
from gatekeeper.seed import data
from gatekeeper.seed.data import ANCHOR, TEAMS, Team

START = ANCHOR - timedelta(days=data.HISTORY_DAYS)
BASE_RATES = {"dependency.max_severity": 0.06, "secrets.allowed": 0.012,
              "sast.new_high_max": 0.10, "tests.min_pass_rate": 0.05, "signing.required": 0.04}
PRESSURE_RATE = 0.55  # a waived problem keeps failing until it is fixed
NOTICE_HOUR = 9
OUTAGE = (datetime(2026, 11, 18, 14, 0, tzinfo=UTC), datetime(2026, 11, 18, 20, 30, tzinfo=UTC))
DEAD_AFTER_S = sum(30 * 2 ** (n - 1) for n in range(1, 8))  # 7 retries, then dead
CHUNK = 5000
_CLAUSE = re.compile(r"\s*(>=|<=|==|>|<)\s*([0-9][0-9.]*)\s*$")
_OPS = {">=": operator.ge, "<=": operator.le, "==": operator.eq, ">": operator.gt,
        "<": operator.lt}


class SeedError(Exception):
    pass


class Service(NamedTuple):
    id: int
    team: Team
    slug: str
    major: int
    minor: int


def generate(conn: Connection, *, seed: int = 7, scale: float = 1.0,
             reset: bool = False) -> dict[str, Any]:
    if reset:
        names = ", ".join(t.name for t in tables.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    elif conn.execute(select(func.count()).select_from(tables.teams)).scalar() or conn.execute(
        select(func.count()).select_from(tables.api_keys)
    ).scalar():
        raise SeedError("the database already has data; run with --reset to replace it")
    return _Builder(conn, seed, scale).run()


def policy_rules(opts: dict[str, Any]) -> list[dict[str, Any]]:
    sast = {"id": "sast.max_high" if opts.get("sast_alias") else "sast.new_high_max",
            "max": opts.get("sast_max", 0), "action": opts.get("sast_action", "warn")}
    if "sast_branches" in opts:
        sast["when"] = {"branches": opts["sast_branches"]}
    rules = [
        {"id": "dependency.max_severity", "max": opts.get("dep_max", "high"), "action": "block"},
        {"id": "secrets.allowed", "max": 0, "action": "block"},
        sast,
        {"id": "tests.min_pass_rate", "min": opts.get("pass_rate", 0.95),
         "action": opts.get("tests_action", "block")},
    ]
    if opts.get("signing", True):
        signing: dict[str, Any] = {"id": "signing.required", "action": "block"}
        when = {"branches": opts["signing_branches"]} if "signing_branches" in opts else {}
        if envs := opts.get("signing_envs", ["production"]):
            when["environments"] = envs
        if when:
            signing["when"] = when
        rules.append(signing)
    return rules


def render_policy(rules: list[dict[str, Any]]) -> str:
    dump = [yaml.safe_dump(r, default_flow_style=True, sort_keys=False, width=200).strip()
            for r in rules]
    return "policy: 1\nrules:\n" + "".join(f"  - {line}\n" for line in dump)


def _canonical(rule_id: str) -> str:
    return "sast.new_high_max" if rule_id == "sast.max_high" else rule_id


def _applies(when: dict[str, Any] | None, branch: str, environment: str) -> bool:
    when = when or {}
    if "branches" in when and not any(fnmatch.fnmatchcase(branch, g) for g in when["branches"]):
        return False
    return "environments" not in when or environment in when["environments"]


def _in_range(version: str | None, spec: str | None) -> bool:
    """Waiver version ranges as the waivers package reads them (no pre-releases in the seed)."""
    def parts(v: str) -> tuple[int, ...]:
        return tuple(int(p) for p in (v.split(".") + ["0", "0"])[:3])

    clauses = [_CLAUSE.match(c).groups() for c in spec.split(",")] if spec else []
    return not clauses or (version is not None and all(
        _OPS[op](parts(version), parts(bound)) for op, bound in clauses))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


class _Builder:
    def __init__(self, conn: Connection, seed: int, scale: float) -> None:
        self.conn, self.seed, self.scale = conn, seed, scale
        self.rng = random.Random(seed)
        self.rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.services: dict[int, Service] = {}
        self.service_ids: dict[tuple[str, str], int] = {}
        self.policies: dict[str, list[tuple[datetime, int, int, list[dict[str, Any]]]]] = {}
        self.active: dict[tuple[str, str], list[tuple]] = defaultdict(list)
        self.pressure: dict[tuple[str, str], list[tuple]] = defaultdict(list)

    def run(self) -> dict[str, Any]:
        self._teams()
        self._bulk(tables.teams, self.rows["teams"])
        self._bulk(tables.services, self.rows["services"])
        self._keys()
        self._policies()
        self._waivers()
        self._evaluations()
        self._finish_outbox()
        audit = sorted(self.rows["audit_events"], key=lambda a: a["created_at"])
        self.rows["audit_events"] = [{**event, "id": i} for i, event in enumerate(audit, 1)]
        summary: dict[str, Any] = {}
        for table in tables.metadata.sorted_tables:
            if "id" not in table.c:
                continue
            if table.name not in ("teams", "services", "api_keys"):  # inserted before the keys
                self._bulk(table, self.rows[table.name])
            sequence = func.pg_get_serial_sequence(table.name, "id")
            top = select(func.coalesce(func.max(table.c.id), 0) + 1).scalar_subquery()
            self.conn.execute(select(func.setval(sequence, top, False)))
            summary[table.name] = len(self.rows[table.name])
        summary["api_keys"] = len(TEAMS) + len(data.REVIEWER_KEYS)
        for name in ("waivers", "callback_outbox"):
            summary[name] = dict(Counter(row["status"] for row in self.rows[name]))
        return summary

    def _bulk(self, table: Table, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), CHUNK):
            self.conn.execute(insert(table), rows[i:i + CHUNK])

    def _audit(self, at: datetime, actor: str, action: str, subject_type: str,
               subject_id: int | None, team_id: int | None, details: dict[str, Any]) -> None:
        self.rows["audit_events"].append({"team_id": team_id, "actor": actor, "action": action,
                           "subject_type": subject_type, "subject_id": subject_id,
                           "details": details, "created_at": at})

    def _teams(self) -> None:
        for team in TEAMS:
            created = ANCHOR - timedelta(days=team.created_days)
            self.rows["teams"].append({
                "id": team.id, "slug": team.slug, "name": team.name, "timezone": team.timezone,
                "callback_secret": data.callback_secret(team.slug),
                "notify_url": f"{data.CI_MOCK}/notify/{team.slug}", "created_at": created,
            })
            self._audit(created, "seed", "team.created", "team", team.id, team.id,
                        {"name": team.name})
            for spec in team.services.split():
                slug, line = spec.split(":")
                major, minor = (int(p) for p in line.split("."))
                sid = len(self.services) + 1
                self.services[sid] = Service(sid, team, slug, major, minor)
                self.service_ids[(team.slug, slug)] = sid
                name = " ".join(w.upper() if w in ("api", "sgd", "kyc", "ui", "pin") else
                                w.capitalize() for w in slug.split("-"))
                self.rows["services"].append({"id": sid, "team_id": team.id, "slug": slug,
                                              "name": name, "created_at": created})

    def _keys(self) -> None:
        issued = [(f"{t.slug}-ci", ROLE_TEAM, t.id, t.created_days) for t in TEAMS]
        issued += [(name, ROLE_REVIEWER, None, 790) for name in data.REVIEWER_KEYS]
        for name, role, team_id, days in issued:
            key_id, _ = issue_key(self.conn, name=name, role=role, team_id=team_id,
                                  key=data.seeded_key(name))
            at = ANCHOR - timedelta(days=days, hours=-1)
            self.conn.execute(update(tables.api_keys).where(tables.api_keys.c.id == key_id)
                              .values(created_at=at))
            self._audit(at, "seed", "key.issued", "api_key", key_id, team_id,
                        {"name": name, "role": role})

    def _policies(self) -> None:
        team_ids = {t.slug: t.id for t in TEAMS}
        for pid, (slug, days, author, comment, opts) in enumerate(
            sorted(data.POLICIES, key=lambda p: -p[1]), 1
        ):
            history = self.policies.setdefault(slug, [])
            created, rules = ANCHOR - timedelta(days=days, hours=-3), policy_rules(opts)
            history.append((created, pid, len(history) + 1, rules))
            self.rows["policies"].append({
                "id": pid, "team_id": team_ids[slug], "version": len(history),
                "source": render_policy(rules), "comment": comment,
                "created_by": f"key:{author}", "created_at": created,
            })
            self._audit(created, f"key:{author}", "policy.published", "policy", pid,
                        team_ids[slug], {"version": len(history), "comment": comment})

    def _waivers(self) -> None:
        teams = {t.slug: t for t in TEAMS}
        for wid, w in enumerate(sorted(data.WAIVERS, key=lambda w: -w.created_days), 1):
            team = teams[w.team]
            sid = self.service_ids[(w.team, w.service)] if w.service else None
            created = ANCHOR - timedelta(days=w.created_days)
            expires = ANCHOR + timedelta(hours=w.expires_hours)
            requester, reviewer = f"key:{w.team}-ci", f"key:{data.REVIEWER_KEYS[wid % 2]}"
            row = {"id": wid, "team_id": team.id, "service_id": sid, "rule": w.rule,
                   "version_range": w.version_range, "reason": w.reason,
                   "requested_by": requester, "status": w.status, "reviewed_by": None,
                   "reviewed_at": None, "review_note": None, "expires_at": expires,
                   "expiry_notice_sent_at": None, "created_at": created}
            self.rows["waivers"].append(row)
            base = {"rule": w.rule, "service_id": sid, "expires_at": expires.isoformat()}

            def audit(at, actor, action, note=None, team=team, wid=wid, base=base):
                self._audit(at, actor, action, "waiver", wid, team.id, {**base, "note": note})

            audit(created, requester, "waiver.requested")
            end = created + timedelta(days=5)
            if w.status == "rejected":
                reviewed = created + timedelta(hours=3)
                row.update(reviewed_by=reviewer, reviewed_at=reviewed, review_note=w.note)
                audit(reviewed, reviewer, "waiver.rejected", w.note)
            elif w.status != "pending" and (w.status != "expired" or w.note):
                approved = created + timedelta(hours=2 + wid % 5)
                end = ANCHOR - timedelta(days=w.revoked_days) if w.revoked_days else expires
                row.update(reviewed_by=reviewer, reviewed_at=approved,
                           review_note=None if w.revoked_days else w.note)
                audit(approved, reviewer, "waiver.approved", None if w.revoked_days else w.note)
                if w.revoked_days:  # the row keeps the approval; the audit log has the revoke
                    audit(end, requester, "waiver.revoked", w.note)
                self.active[(w.team, w.rule)].append(
                    (approved, end, w.service, w.version_range, wid, expires))
                self._notice(team, w.service, row, approved, min(end, ANCHOR))
            if w.status == "expired":
                self._audit(expires + timedelta(seconds=17), "scheduler", "waiver.expired",
                            "waiver", wid, team.id, {"expires_at": expires.isoformat()})
            self.pressure[(w.team, w.rule)].append(
                (created - timedelta(days=3), min(end, ANCHOR) + timedelta(days=1), w.service,
                 w.advisory))

    def _notice(self, team: Team, service: str | None, row: dict[str, Any], approved: datetime,
                end: datetime) -> None:
        """When the scheduler sent ``waiver.expiring``: hour 09 local, within 72 h of expiry."""
        start = max(approved, row["expires_at"] - timedelta(hours=72)).astimezone(
            ZoneInfo(team.timezone))
        at = start.replace(hour=NOTICE_HOUR, minute=0, second=12, microsecond=0)
        if start.hour == NOTICE_HOUR:
            at = start + timedelta(seconds=12)
        elif at < start:
            at += timedelta(days=1)
        at = at.astimezone(UTC)
        if at >= end:
            return
        row["expiry_notice_sent_at"] = at
        view = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items()
                if k not in ("team_id", "service_id")}
        self.rows["callback_outbox"].append({
            "team_id": team.id, "evaluation_id": None, "event": "waiver.expiring",
            "url": f"{data.CI_MOCK}/notify/{team.slug}",
            "payload": {"event": "waiver.expiring", "team": team.slug,
                        "waiver": {**view, "team": team.slug, "service": service,
                                   "status": "approved"}},
            "status": "delivered", "attempts": 1, "next_attempt_at": at, "last_error": None,
            "created_at": at, "delivered_at": at + timedelta(seconds=2),
        })

    def _when(self, tz: ZoneInfo) -> datetime:
        """A plausible build time: office hours on weekdays, in the team's timezone."""
        while True:
            at = START + timedelta(seconds=self.rng.uniform(0, data.HISTORY_DAYS * 86400))
            local = at.astimezone(tz)
            if local.weekday() >= 5 and self.rng.random() > 0.12:
                continue
            if not 8 <= local.hour < 20 and self.rng.random() > 0.08:
                continue
            return at.replace(microsecond=0)

    def _evaluations(self) -> None:
        slots = []
        for team in TEAMS:
            tz = ZoneInfo(team.timezone)
            sids = [s.id for s in self.services.values() if s.team is team]
            for _ in range(round(team.weight * self.scale)):
                slots.append((self._when(tz), team.id, self.rng.choice(sids)))
        slots.sort()
        for eid, (at, _, sid) in enumerate(slots, 1):
            self._evaluation(eid, at, self.services[sid])

    def _evaluation(self, eid: int, at: datetime, svc: Service) -> None:
        rng, team = self.rng, svc.team
        env = rng.choices(("production", "staging", "development"), (55, 30, 15))[0]
        line = f"{svc.major}.{svc.minor + (at - START).days // 14}"
        if env == "development":
            branch = f"feature/{team.slug[:3].upper()}-{rng.randint(100, 2400)}"
        elif rng.random() < 0.7:
            branch = "main"
        else:
            branch = f"release/{line}"
        version = None if env == "development" else f"{line}.{rng.randint(0, 4)}"
        evidence = self._passing_evidence(svc, rng)
        history = self.policies.get(team.slug, [])
        index = bisect.bisect_right([p[0] for p in history], at) - 1
        policy = history[index] if index >= 0 else None
        reasons = []
        if policy is None:
            reasons.append({"rule": "policy.missing", "outcome": "warn",
                            "message": "team has no policy; publish one with POST /v1/policies",
                            "waiver_id": None, "details": {}})
        for rule in policy[3] if policy else []:
            rule_id = _canonical(rule["id"])
            if not _applies(rule.get("when"), branch, env):
                continue
            pressure = self._pressure(team.slug, rule_id, svc.slug, at)
            rate = PRESSURE_RATE if pressure else BASE_RATES[rule_id] * team.risk
            if rng.random() >= rate:
                continue
            message, details = getattr(self, "_violate_" + rule_id.split(".")[0])(
                rule, evidence, pressure, svc)
            outcome, waiver_id = rule["action"], self._match(team.slug, rule_id, svc.slug,
                                                              version, at)
            if waiver_id:
                outcome, message = "warn", "waived: " + message
                self._audit(at, f"key:{team.slug}-ci", "waiver.applied", "waiver", waiver_id,
                            team.id, {"evaluation_id": eid, "rule": rule_id})
            reasons.append({"rule": rule_id, "outcome": outcome, "message": message,
                            "waiver_id": waiver_id, "details": details})
        outcomes = {r["outcome"] for r in reasons}
        decision = "block" if "block" in outcomes else "warn" if outcomes else "pass"
        legacy = team.ci == "legacy"
        pipeline_id = f"LR-{at:%Y%m%d}-{eid % 10000:04d}" if legacy else f"fl-{70000 + eid}"
        callback = (f"{data.CI_MOCK}/callbacks/{team.slug}/{svc.slug}"
                    if rng.random() < (0.7 if legacy else 0.95) else None)
        row = {"id": eid, "team_id": team.id, "service_id": svc.id,
               "policy_id": policy[1] if policy else None, "source": team.ci,
               "pipeline_id": pipeline_id, "commit_sha": f"{rng.getrandbits(160):040x}",
               "branch": branch, "environment": env, "version": version, "decision": decision,
               "reasons": reasons, "callback_url": callback,
               "idempotency_key": None if legacy else f"{pipeline_id}:1",
               "payload_sha256": hashlib.sha256(f"{self.seed}:{eid}".encode()).hexdigest(),
               "created_at": at}
        self.rows["evaluations"].append(row)
        for kind, payload in evidence.items():
            self.rows["evidence"].append({"id": len(self.rows["evidence"]) + 1,
                                          "evaluation_id": eid, "kind": kind, "data": payload})
        self._audit(at, f"key:{team.slug}-ci", "evaluation.decided", "evaluation", eid, team.id,
                    {"decision": decision, "policy_version": policy[2] if policy else None,
                     "rules": [r["rule"] for r in reasons],
                     "waiver_ids": [r["waiver_id"] for r in reasons if r["waiver_id"]]})
        if callback:
            view = {"id": eid, "team": team.slug, "service": svc.slug, "source": team.ci,
                    **{k: row[k] for k in ("pipeline_id", "commit_sha", "branch", "environment",
                                           "version", "decision", "reasons")},
                    "policy_version": policy[2] if policy else None,
                    "created_at": at.isoformat()}
            self._enqueue(team, eid, callback, view, at)

    def _passing_evidence(self, svc: Service, rng: random.Random) -> dict[str, Any]:
        ecosystem = "npm" if svc.team.slug in data.NPM_TEAMS else "pypi"
        packages = [{"name": name, "ecosystem": ecosystem, "vulnerabilities": [],
                     "version": f"{rng.randint(0, 5)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}"}
                    for name in rng.sample(data.PACKAGES[ecosystem], 4)]
        if rng.random() < 0.2:
            packages[0]["vulnerabilities"].append(
                {"id": f"MBSA-2026-{rng.randint(100, 999):04d}", "severity": "low"})
        total = 120 + zlib.crc32(svc.slug.encode()) % 800
        failed = 0 if rng.random() < 0.85 else rng.randint(1, max(1, total // 100))
        skipped = rng.randint(0, 12)
        legacy = svc.team.ci == "legacy"
        return {
            "dependencies": {"packages": packages},
            "secrets": {"count": 0, "findings": []},
            "sast": {"new": {"critical": 0, "high": 0, "medium": rng.randint(0, 3),
                             "low": rng.randint(0, 6)},
                     "total": None if legacy else {"critical": 0, "high": rng.randint(0, 5),
                                                   "medium": rng.randint(5, 30),
                                                   "low": rng.randint(10, 60)}},
            "tests": {"passed": total - failed - skipped, "failed": failed, "skipped": skipped},
            "signing": {"signed": True, "verified": True,
                        "key_id": None if legacy else "mossbank-release-2026"},
        }

    def _violate_dependency(self, rule, evidence, pressure, svc):
        packages = evidence["dependencies"]["packages"]
        if pressure and pressure[3]:
            name, version, advisory = pressure[3]
        elif pressure:  # the same advisory keeps failing while the waiver story runs
            crc = zlib.crc32(f"{svc.slug}:{rule['id']}".encode())
            pool = data.PACKAGES[packages[0]["ecosystem"]]
            name, version = pool[crc % len(pool)], f"{crc % 5}.{crc % 17}.{crc % 7}"
            advisory = f"MBSA-2026-{crc % 900 + 100:04d}"
        else:
            package = self.rng.choice(packages)
            name, version = package["name"], package["version"]
            advisory = f"MBSA-2026-{self.rng.randint(100, 999):04d}"
        above = SEVERITIES[severity_rank(rule["max"]) + 1:]
        severity = "critical" if pressure else self.rng.choice(above)
        if pressure:  # the waived package replaces one of the sampled ones
            packages[:] = [p for p in packages if p["name"] != name][:3] + [
                {"name": name, "version": version, "ecosystem": packages[0]["ecosystem"],
                 "vulnerabilities": []}]
        package = next(p for p in packages if p["name"] == name)
        package["vulnerabilities"].append({"id": advisory, "severity": severity})
        return (f"{name} {version}: {advisory} is {severity} (max {rule['max']})",
                {"violations": [{"package": name, "id": advisory, "severity": severity}],
                 "count": 1, "max": rule["max"]})

    def _violate_secrets(self, rule, evidence, pressure, svc):
        count = self.rng.randint(1, 2)
        findings = [] if svc.team.ci == "legacy" else [
            {"detector": self.rng.choice(data.SECRET_DETECTORS), "path": "deploy/app.env",
             "line": self.rng.randint(1, 40)} for _ in range(count)]
        evidence["secrets"] = {"count": count, "findings": findings}
        return (f"{_plural(count, 'secret finding')} (max {rule['max']})",
                {"count": count, "max": rule["max"]})

    def _violate_sast(self, rule, evidence, pressure, svc):
        count = rule["max"] + self.rng.randint(1, 2)
        new = evidence["sast"]["new"]
        new["critical"] = 1 if count > 1 and self.rng.random() < 0.3 else 0
        new["high"] = count - new["critical"]
        if evidence["sast"]["total"]:
            evidence["sast"]["total"]["high"] += new["high"]
        return (f"{_plural(count, 'new high SAST finding')} (max {rule['max']})",
                {"new_high": count, "max": rule["max"]})

    def _violate_tests(self, rule, evidence, pressure, svc):
        tests = evidence["tests"]
        ran = tests["passed"] + tests["failed"]
        failed = int(ran * (1 - rule["min"])) + self.rng.randint(1, 8)
        tests.update(passed=ran - failed, failed=failed)
        rate = (ran - failed) / ran
        return (f"pass rate {rate:.1%} (min {rule['min'] * 100:g}%)",
                {**tests, "rate": round(rate, 4), "min": rule["min"]})

    def _violate_signing(self, rule, evidence, pressure, svc):
        signed = self.rng.random() < 0.4
        key_id = evidence["signing"]["key_id"] if signed else None
        evidence["signing"] = {"signed": signed, "verified": False, "key_id": key_id}
        message = (f"signature by {key_id or 'an unknown key'} is not verified" if signed
                   else "release is not signed")
        return message, dict(evidence["signing"])

    def _pressure(self, team: str, rule: str, service: str, at: datetime) -> tuple | None:
        for entry in self.pressure.get((team, rule), ()):
            if entry[0] <= at < entry[1] and entry[2] in (None, service):
                return entry
        return None

    def _match(self, team: str, rule: str, service: str, version: str | None,
               at: datetime) -> int | None:
        """The waiver the evaluator would apply: the one expiring last, then the lowest id."""
        matches = [(expires, -wid) for start, end, svc, spec, wid, expires
                   in self.active.get((team, rule), ())
                   if start <= at < end and svc in (None, service) and _in_range(version, spec)]
        return -max(matches)[1] if matches else None

    def _enqueue(self, team: Team, eid: int, url: str, view: dict[str, Any],
                 at: datetime) -> None:
        entry = {"team_id": team.id, "evaluation_id": eid, "event": "evaluation.decided",
                 "url": url, "payload": {"event": "evaluation.decided", "evaluation": view},
                 "status": "delivered", "attempts": 1, "next_attempt_at": at,
                 "last_error": None, "created_at": at,
                 "delivered_at": at + timedelta(seconds=self.rng.uniform(1, 35))}
        age = ANCHOR - at
        if team.slug == "merchant-portal" and OUTAGE[0] <= at < OUTAGE[1]:
            if at + timedelta(seconds=DEAD_AFTER_S) < OUTAGE[1]:
                entry.update(status="dead", attempts=8, delivered_at=None,
                             next_attempt_at=at + timedelta(seconds=DEAD_AFTER_S),
                             last_error="HTTP 503 Service Unavailable")
            else:
                entry.update(attempts=5, delivered_at=OUTAGE[1] + timedelta(seconds=40))
        elif age < timedelta(minutes=20):
            entry.update(status="pending", attempts=0, delivered_at=None)
        elif team.slug == "risk-scoring" and age < timedelta(hours=1):
            entry.update(status="pending", attempts=2, delivered_at=None,
                         last_error="timed out after 5s",
                         next_attempt_at=ANCHOR + timedelta(seconds=40))
        self.rows["callback_outbox"].append(entry)

    def _finish_outbox(self) -> None:
        outbox = self.rows["callback_outbox"]
        outbox.sort(key=lambda o: (o["created_at"], o["evaluation_id"] or 0))
        for oid, entry in enumerate(outbox, 1):
            entry["id"] = oid
            if entry["status"] == "dead":
                self._audit(entry["next_attempt_at"], "scheduler", "callback.dead", "callback",
                            oid, entry["team_id"],
                            {"event": entry["event"], "attempts": 8,
                             "last_error": entry["last_error"]})
