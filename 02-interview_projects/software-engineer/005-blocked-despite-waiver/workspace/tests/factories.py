"""Row builders for tests. Every argument has a sensible default and a
missing parent is created on the fly (``factory.evaluation()`` makes a team
and a service). Builders return the inserted ``Row``; key builders return the
plaintext key.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Row, Table, func, insert, select

from gatekeeper.core import tables
from gatekeeper.core.auth import ROLE_REVIEWER, ROLE_TEAM, issue_key

TODAY = datetime(2026, 12, 2, 11, 0, tzinfo=UTC)

DEFAULT_POLICY = """\
policy: 1
rules:
  - {id: dependency.max_severity, max: high, action: block}
  - {id: secrets.allowed, max: 0, action: block}
  - {id: sast.new_high_max, max: 0, action: warn}
  - {id: tests.min_pass_rate, min: 0.95, action: block}
  - {id: signing.required, action: block, when: {environments: [production]}}
"""

PASSING_EVIDENCE: dict[str, dict[str, Any]] = {
    "dependencies": {"packages": [{"name": "flaskwork", "version": "3.0.3", "ecosystem": "pypi",
                                   "vulnerabilities": []}]},
    "secrets": {"count": 0, "findings": []},
    "sast": {"new": {"critical": 0, "high": 0, "medium": 1, "low": 3}, "total": None},
    "tests": {"passed": 412, "failed": 0, "skipped": 6},
    "signing": {"signed": True, "verified": True, "key_id": "mossbank-release-2026"},
}


def auth_header(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


class Factory:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self._seq = itertools.count(1)

    def _insert(self, table: Table, **values: Any) -> Row:
        return self.conn.execute(insert(table).values(**values).returning(table)).one()

    def team(self, slug: str | None = None, **kw: Any) -> Row:
        slug = slug or f"team-{next(self._seq)}"
        kw.setdefault("name", slug.replace("-", " ").title())
        kw.setdefault("callback_secret", f"DEMO-whsec-{slug}-0000test0000")
        kw.setdefault("created_at", TODAY - timedelta(days=400))
        return self._insert(tables.teams, slug=slug, **kw)

    def service(self, team: Row | None = None, slug: str | None = None, **kw: Any) -> Row:
        team = team or self.team()
        slug = slug or f"service-{next(self._seq)}"
        kw.setdefault("name", slug.replace("-", " ").title())
        kw.setdefault("created_at", TODAY - timedelta(days=300))
        return self._insert(tables.services, team_id=team.id, slug=slug, **kw)

    def team_of(self, service: Row) -> Row:
        teams = tables.teams
        return self.conn.execute(select(teams).where(teams.c.id == service.team_id)).one()

    def team_key(self, team: Row | None = None, name: str | None = None) -> str:
        team = team or self.team()
        _, key = issue_key(
            self.conn, name=name or f"{team.slug}-ci", role=ROLE_TEAM, team_id=team.id
        )
        return key

    def reviewer_key(self, name: str = "security-review") -> str:
        _, key = issue_key(self.conn, name=name, role=ROLE_REVIEWER)
        return key

    def policy(self, team: Row | None = None, source: str = DEFAULT_POLICY, **kw: Any) -> Row:
        team = team or self.team()
        if "version" not in kw:
            versions = tables.policies.c
            current = self.conn.execute(
                select(func.max(versions.version)).where(versions.team_id == team.id)
            ).scalar()
            kw["version"] = (current or 0) + 1
        kw.setdefault("created_by", "key:security-review")
        kw.setdefault("created_at", TODAY - timedelta(days=30))
        return self._insert(tables.policies, team_id=team.id, source=source, **kw)

    def evaluation(
        self,
        service: Row | None = None,
        evidence_data: dict[str, dict[str, Any]] | None = None,
        **kw: Any,
    ) -> Row:
        service = service or self.service()
        n = next(self._seq)
        kw.setdefault("source", "forgeline_v2")
        kw.setdefault("pipeline_id", f"fl-{40000 + n}")
        kw.setdefault("commit_sha", f"{n:040x}")
        kw.setdefault("branch", "main")
        kw.setdefault("environment", "production")
        kw.setdefault("version", "1.0.0")
        kw.setdefault("decision", "pass")
        kw.setdefault("reasons", [])
        kw.setdefault("created_at", TODAY - timedelta(hours=1))
        row = self._insert(tables.evaluations, team_id=service.team_id, service_id=service.id, **kw)
        if evidence_data is None:
            evidence_data = PASSING_EVIDENCE
        for kind, data in evidence_data.items():
            self._insert(tables.evidence, evaluation_id=row.id, kind=kind, data=data)
        return row

    def waiver(self, team: Row | None = None, service: Row | None = None, **kw: Any) -> Row:
        if team is None:
            team = self.team_of(service) if service is not None else self.team()
        kw.setdefault("rule", "dependency.max_severity")
        kw.setdefault("reason", "fix scheduled for the next sprint")
        kw.setdefault("requested_by", f"key:{team.slug}-ci")
        kw.setdefault("status", "approved")
        if kw["status"] != "pending":
            kw.setdefault("reviewed_by", "key:security-review")
            kw.setdefault("reviewed_at", TODAY - timedelta(days=1))
        kw.setdefault("expires_at", TODAY + timedelta(days=14))
        kw.setdefault("created_at", TODAY - timedelta(days=2))
        service_id = service.id if service is not None else None
        return self._insert(tables.waivers, team_id=team.id, service_id=service_id, **kw)

    def audit_event(self, team: Row | None = None, **kw: Any) -> Row:
        kw.setdefault("actor", "key:security-review")
        kw.setdefault("action", "policy.published")
        kw.setdefault("subject_type", "policy")
        kw.setdefault("details", {})
        kw.setdefault("created_at", TODAY)
        return self._insert(tables.audit_events, team_id=team.id if team else None, **kw)

    def outbox(self, team: Row | None = None, **kw: Any) -> Row:
        team = team or self.team()
        kw.setdefault("event", "evaluation.decided")
        kw.setdefault("url", f"http://ci-mock:9100/callbacks/{team.slug}")
        kw.setdefault("payload", {"event": kw["event"]})
        kw.setdefault("next_attempt_at", TODAY)
        kw.setdefault("created_at", TODAY)
        return self._insert(tables.callback_outbox, team_id=team.id, **kw)
