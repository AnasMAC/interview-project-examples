# GATE-398: Warn-only mode for teams migrating off the legacy runner

- Reporter: Elif Yıldız (product, developer experience)
- Opened: 2026-11-16
- Priority: P2
- Teams: kyc-platform, treasury-tools, data-pipelines

## Problem

Three teams still build on the legacy runner and must move to Forgeline CI
before the runner is switched off on 2027-03-01. The migration plan has each
team run both pipelines side by side for a few weeks. The new Forgeline
pipelines send richer evidence (full secret findings, SAST totals, signing
key ids), so on day one they are evaluated more strictly than the legacy
ones and start blocking releases that the legacy pipeline lets through.
Teams then pause the migration, which is the opposite of what we want.

Data Pipelines tried it last week: 9 of their first 14 Forgeline runs were
blocked, mostly on `secrets.allowed`: the Forgeline secrets scan also reads
test fixtures, which the legacy runner's scanner always skipped.

## What we want

A **warn-only** mode a security reviewer can turn on for a team (optionally
for one CI source) for a limited period:

- Gatekeeper still evaluates every rule and stores the real outcome, but a
  `block` is returned to CI as `warn` while the mode is on.
- The response and the callback say clearly that the decision was softened,
  and what it would have been, so dashboards and the scorecard can count
  "would have blocked".
- It has an end date (at most 60 days) and expires by itself, like a waiver.
- Turning it on and off is audited with who, when and why.
- Team keys can see whether their team is in warn-only mode but cannot
  change it.

## Acceptance

- A reviewer enables the mode for `data-pipelines`, source `forgeline_v2`,
  until 2027-01-31; a Forgeline run that violates a blocking rule gets
  `warn`, the legacy run of the same commit is unaffected.
- After the end date the same run blocks again without anyone acting.
- The audit log shows the change; the scorecard shows how many decisions
  were softened per team.
- Policy semantics stay as documented for every team not in the mode.

## Out of scope

Per-rule exceptions (that is what waivers are for) and changes to the
legacy adapter.
