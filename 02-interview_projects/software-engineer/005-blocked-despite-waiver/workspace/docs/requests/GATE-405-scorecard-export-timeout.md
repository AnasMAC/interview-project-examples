# GATE-405: Scorecard CSV export times out

- Reporter: Mariana Silva (on behalf of the quarterly security review)
- Opened: 2026-11-25
- Priority: P2
- Component: reporting

## Problem

For the Q4 security review Grace needs the evaluation export for the last
quarter, all teams. In production
(`https://gatekeeper.mossbank.example.test`) the request never completes:

```
GET /v1/reports/export.csv?days=92
```

The browser gives up after about 30 seconds with a 502 from the ingress.
`days=30` works but takes around 9 seconds; `days=60` fails about half the
time. Production has roughly 1.9 million evaluations since 1.0 and grows by
about 45,000 a week. The scorecard itself (`/v1/reports/scorecard?days=92`)
answers, but has gone from under a second to about 4 seconds this year.

During the failed attempts the app pods log:

```
[2026-11-25 14:02:31 +0000] [7] [CRITICAL] WORKER TIMEOUT (pid:41)
[2026-11-25 14:02:31 +0000] [41] [INFO] Worker exiting (pid: 41)
[2026-11-25 14:02:32 +0000] [52] [INFO] Booting worker with pid: 52
```

There is no `request.completed` line for those requests, and memory of the
worker climbs past 1 GiB before it is killed. CI evaluations served by the
same pod were slower during the export (p95 of `POST /v1/evaluations` went
from 60 ms to 2.4 s), which worries us more than the report itself.

## Reproduce locally

```sh
make seed SEED_ARGS="--reset --scale 10"
make bench
```

On a laptop the 84-day export of the scale-10 data takes over a second;
production is about 25 times larger.

## Acceptance

- A 92-day all-teams export completes well inside the ingress timeout at
  production volume and does not hold a worker's memory proportional to the
  number of rows.
- Exports do not degrade `POST /v1/evaluations` latency noticeably.
- The CSV columns and their meaning stay the same (finance and audit
  scripts read them).
- `make bench` numbers before and after are in the pull request.
