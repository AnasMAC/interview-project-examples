# GATE-409: Waiver expiry notices arrive at the wrong local time for Singapore

- Reporter: Elif Yıldız, for the Settlement Singapore team
- Opened: 2026-11-19
- Priority: P3
- Component: waivers (expiry notices)

## Report

From the Settlement Singapore team lead:

> Our waiver expiry notices arrive at 17:00 Singapore time, after our
> release window has closed and most of the team has left. The notice for
> the `sgd-clearing` SAST waiver (expiring Friday 20 November, 19:00 SGT)
> reached our notify channel on Wednesday at 17:00:12. On Thursday nobody
> had picked it up and the waiver lapsed during Friday's settlement batch
> release, which was then blocked. We understood from the docs that notices
> are sent at 09:00 in the team's own time zone.

Our London teams say their notices arrive at 09:00 as expected. The Dublin
and Lisbon teams have not noticed anything wrong. Merchant Portal (New York)
said they "sometimes get them in the middle of the night" but has no example.

## Evidence

From the ci-mock style receiver the team runs in staging
(`var/ci-mock/callbacks.jsonl`, trimmed):

```json
{"body": {"event": "waiver.expiring", "team": "settlement-sg",
          "waiver": {"service": "sgd-clearing", "rule": "sast.new_high_max",
                     "expires_at": "2026-11-20T11:00:00+00:00",
                     "expiry_notice_sent_at": "2026-11-18T09:00:12+00:00", "...": "..."}},
 "delivery": "5208", "event": "waiver.expiring", "path": "/notify/settlement-sg",
 "received_at": "2026-11-18T09:00:14.093+00:00", "signature_valid": true,
 "timestamp": "1794992414"}
```

The team's timezone in Gatekeeper is `Asia/Singapore`.

## Acceptance

- Notices go out during the 09:00 hour in each team's configured time zone,
  for every team, including time zones with daylight saving time.
- Each waiver still gets exactly one notice.
- A test covers a team east of UTC and one west of UTC.
