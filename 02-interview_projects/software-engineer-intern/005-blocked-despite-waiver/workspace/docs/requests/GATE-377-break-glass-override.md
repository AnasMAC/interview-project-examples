# GATE-377: Break-glass emergency override, with audit

- Reporter: Grace Adeyemi (platform security), with Kwame Boateng (SRE)
- Opened: 2026-10-29
- Priority: P2
- Component: evaluation / audit / API

## Background

During the refunds incident on 24 October the fix for `refunds-worker` was
blocked by `tests.min_pass_rate`: two acquirer sandbox tests were failing
for reasons unrelated to the fix. The only way through was a waiver, which
meant waking a security reviewer at 02:10, writing a request, approving it
and re-running the pipeline. It took 50 minutes. The waiver was then left
in place for a week because nobody remembered to revoke it.

Waivers are the right tool for known, planned exceptions. They are the
wrong tool for "production is down and this one build must ship now".

## What we want

A **break-glass** override for a single evaluation:

- Allowed for security reviewers and for a short list of on-call
  engineers per team (new permission; team CI keys must never be able to
  use it).
- Applies to one evaluation (or pipeline id), not to future builds; the
  next build is evaluated normally.
- Requires a reason and an incident reference (`INC-` number).
- Turns the decision into `pass` for that release, while keeping the
  original outcome and reasons visible in the evaluation, the callback and
  the CSV export.
- Every use writes an audit event in the same transaction as the override,
  and notifies `#platform-security` through the team's notify URL.
- A team cannot use it more than twice in 24 hours without a reviewer.

## Acceptance

- An on-call engineer overrides a blocked evaluation; CI receives a signed
  `evaluation.overridden` callback and can release.
- The override cannot be applied by a team CI key, to another team's
  evaluation (404), or to an evaluation older than 24 hours.
- `GET /v1/audit?action=evaluation.overridden` lists who, when, why and the
  incident; nothing about the override is possible without an audit row.
- The scorecard counts overrides per team.

## Notes

Security wants a review of the authorization design before code is merged:
this is exactly the kind of feature that becomes a permanent bypass.
