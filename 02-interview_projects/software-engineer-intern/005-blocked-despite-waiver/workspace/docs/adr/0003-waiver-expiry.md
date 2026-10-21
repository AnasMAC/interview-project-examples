# ADR 0003: Waiver expiry

- Status: accepted
- Date: 2025-02-24
- Deciders: Grace Adeyemi, Mariana Silva

## Context

Waivers (2.0) let a team ship despite a known violation for a limited time.
A waiver that outlives its reason is a hidden hole in the gate, so expiry
must be automatic and visible. Teams asked for expiry to be predictable:
"valid until the 14th" should mean the same thing to everyone, whichever
office they sit in.

## Decision

- Every waiver has an `expires_at`, at most 90 days after the request
  (`GATE_WAIVER_MAX_DAYS`).
- Waivers expire at **midnight UTC** at the end of their expiry date: a
  waiver with `expires_at` on 2025-03-14 covers releases until
  2025-03-14T23:59:59Z and stops matching at 2025-03-15T00:00:00Z.
- The scheduler's `expire_waivers` job moves due waivers to `expired` and
  writes a `waiver.expired` audit event with actor `scheduler`. Pending
  waivers that were never reviewed expire the same way.
- An expired waiver is never reactivated; the team requests a new one.
- Teams are warned before expiry by a `waiver.expiring` notice (added with
  the notices work; see the 3.1 changelog).

## Consequences

- One rule for every team, easy to explain in the waiver form.
- A waiver requested for "two weeks" at 16:00 gets a few hours more than
  two weeks; we accept the slack.
- Matching must apply the same cut-off as the job, or a waiver could keep
  matching between midnight and the next scheduler run.
