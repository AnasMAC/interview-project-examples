# REQ-0058: Stop the SLA clock while a risk is accepted

| | |
|---|---|
| From | Hana Sato (engineering manager, Payments) |
| Date | 2026-09-10 |
| Priority | Medium; quarterly security review on 2026-10-12 |
| Status | Open, agreed in principle by Samuel Okafor (SLA policy owner) |

## Request

> Every Monday the Payments report shows close to 90 SLA breaches, and a good
> part of them are findings we formally accepted: the WAF rule for the
> refund endpoint (SEC-311), the legacy payouts batch that is switched off
> in Q4, and similar. Those were signed off by Jonas and are reviewed every
> quarter. They still count as breaches, our `sla-check` CI gate keeps
> failing on them, and the number I report upwards is meaningless.
>
> What we want: while a finding is triaged `accepted_risk`, its SLA clock
> does not run. If the acceptance is withdrawn (triage set back to
> `untriaged` or `confirmed`), the clock continues from where it stopped,
> not from zero; we should not get a fresh 30 days for something we
> sat on.
> -- Hana

## Notes from Samuel

- Policy is fine with this, with conditions: the pause only applies while
  the triage is `accepted_risk`; the time already spent before acceptance
  counts; a finding that was already overdue when it was accepted stays
  visible as "accepted, was overdue" in the report so it does not just
  disappear.
- Today `find_breaches` counts accepted risk as a breach on purpose (see
  its docstring). The weekly report, `sla-check`, the teams summary in the
  API and the CSV export all need to agree after the change.
- Reopened findings already restart their clock from the reopen date; that
  rule does not change.
- Triage is set through the API (`POST /api/v1/findings/{id}/triage`) and
  the CLI (`ledger triage`). Both write a `triage` event, so the history of
  when a risk was accepted and withdrawn is in `finding_events`.
- Existing data: about 250 findings in the demo database (and a few hundred
  on the shared instance) are `accepted_risk` today. Decide what their
  clock looks like after the change and say so in the PR.
- Due dates are in business days (`config/holidays.toml`).
