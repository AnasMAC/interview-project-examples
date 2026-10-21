# GATE-412: Payments API release blocked although the waiver is approved

- Reporter: Ben Carter (Payments API)
- Opened: 2026-12-02 10:05 UTC
- Priority: P1 (production release held)
- Component: evaluation / waivers

## What happened

We have an approved waiver for the ledgerkit advisory on `payments-api`
(waiver 16, approved by security on 23 November, valid until 14 December,
for the 4.12 line). Yesterday our 4.12 builds went through with a warning
as expected. This morning the production release of **4.12.3** from `main`
was blocked on exactly that advisory. Nothing changed in our pipeline or in
our dependencies between the two runs; the lock file is identical.

We retried the job (same `Idempotency-Key`) and got the same answer, then
ran a fresh pipeline (`fl-81204`): blocked again. The 10:00 release window
for the acquirer change is missed; we need to know whether the waiver can be
trusted for the 14:00 window.

## Decision returned to Forgeline

```json
{"id": 8137, "team": "payments-api", "service": "payments-api", "source": "forgeline_v2",
 "pipeline_id": "fl-81197", "commit_sha": "c41e0a9b7d2f6e15a8c3b90d4e7f21a6b5c8d903",
 "branch": "main", "environment": "production", "version": "4.12.3", "decision": "block",
 "reasons": [
   {"rule": "dependency.max_severity", "outcome": "block",
    "message": "ledgerkit 2.4.1: MBSA-2026-0141 is critical (max high)", "waiver_id": null,
    "details": {"violations": [{"package": "ledgerkit", "id": "MBSA-2026-0141",
                                "severity": "critical"}], "count": 1, "max": "high"}}],
 "policy_version": 4, "created_at": "2026-12-02T09:41:07+00:00"}
```

And the waiver, as `GET /v1/waivers/16` shows it right now:

```json
{"id": 16, "team": "payments-api", "service": "payments-api",
 "rule": "dependency.max_severity", "version_range": ">=4.12.0,<4.13.0",
 "status": "approved", "reviewed_by": "key:security-review",
 "reviewed_at": "2026-11-23T14:00:00+00:00", "review_note": "approved for the 4.12 line only",
 "expires_at": "2026-12-14T11:00:00+00:00", "expiry_notice_sent_at": null}
```

## Logs (app, 09:41 UTC)

```
{"ts": "2026-12-02T09:41:07.212+00:00", "level": "INFO", "logger": "gatekeeper.ingest.service", "service": "app", "msg": "ingest.evaluation_decided", "evaluation_id": 8137, "team_id": 1, "decision": "block"}
{"ts": "2026-12-02T09:41:07.215+00:00", "level": "INFO", "logger": "gatekeeper.http", "service": "app", "msg": "request.completed", "request_id": "fl-81197-a1", "method": "POST", "path": "/v1/evaluations", "status": 201, "duration_ms": 48.3, "key": "payments-api-ci", "team_id": 1}
{"ts": "2026-12-02T09:44:52.871+00:00", "level": "INFO", "logger": "gatekeeper.ingest.service", "service": "app", "msg": "ingest.idempotent_replay", "evaluation_id": 8137}
{"ts": "2026-12-02T09:44:52.873+00:00", "level": "INFO", "logger": "gatekeeper.http", "service": "app", "msg": "request.completed", "request_id": "fl-81197-a2", "method": "POST", "path": "/v1/evaluations", "status": 200, "duration_ms": 11.9, "key": "payments-api-ci", "team_id": 1}
```

For comparison, yesterday's production run of 4.12.3 (`fl-77922`, evaluation
7922) came back `warn` with `waiver_id: 16`.

## Asks

1. Why did the same build get a different answer today?
2. Can we release at 14:00 without someone approving a second waiver?
3. If this can happen to a waiver, how do we know which other teams are
   affected?

## Attachments

Added by Kwame Boateng, 10:20 UTC, in `GATE-412-attachments/`:

- `app-2026-12-02.jsonl`: production app log of `gk-prod-app-1`, 07:00 to
  10:05 UTC, as exported from the log collector (one JSON object per line).
- `decisions-2026-12-02.csv`: every evaluation stored between 07:00 and
  10:05 UTC (psql export of `evaluations` joined to team, service and policy
  version; `reasons_json` exactly as stored).
- `waivers-2026-12-02.csv`: the `waivers` table at 10:10 UTC. Nobody
  approved, rejected or revoked a waiver today.

These are production data. Your local stack has the demo seed, whose
evaluation ids overlap with these but are different rows.

## Comments

**Kwame Boateng (SRE), 10:20 UTC.** Logs and exports attached. For the
timeline: 3.6.1 went out at 07:31 with Mariana's latency work (and the
dev-clock change, which does nothing in prod); you can see
`deploy.started` / `deploy.finished` in the log. No config, database or
policy changes today, and the app has not restarted since the deploy.

**Grace Adeyemi (platform security), 10:31 UTC.** I am not approving a
duplicate of waiver 16 as a workaround until we know why 16 was ignored;
the runbook's "short waiver" step is for when we understand the cause, and
I do not want two approvals for one advisory in the audit trail. Ben needs
straight answers to his three asks before the 14:00 window, and if other
teams were hit I want to tell them today. Mariana is off until Thursday, so
this is ours.
