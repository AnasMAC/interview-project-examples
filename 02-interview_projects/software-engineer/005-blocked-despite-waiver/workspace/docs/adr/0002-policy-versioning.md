# ADR 0002: Policies are immutable versions

- Status: accepted
- Date: 2024-10-01
- Deciders: Grace Adeyemi, Tobias Krüger

## Context

A decision is only explainable if we know exactly which rules produced it.
In the pilot, teams edited their policy in place, and when a release was
blocked on Monday nobody could tell whether Friday's rules or Monday's had
applied. Auditors asked the same question for the PCI scope.

## Decision

- A policy is stored as rows in `policies` keyed by `(team_id, version)`;
  versions are 1, 2, 3... per team. Publishing inserts `max(version) + 1`.
  Rows are never updated or deleted.
- The **active policy** of a team is its highest version. There is no
  "draft" or "scheduled" state; use the dry run to try a draft.
- Every evaluation stores `policy_id`, so the exact YAML behind any decision
  can be read back with `GET /v1/policies/<version>`.
- Each publish is audited as `policy.published` with the version and the
  author's comment.
- The compiled form of a policy is cached per policy version (not per
  team); a new version is a new cache entry, and nothing has to be
  invalidated.
- Rolling back means publishing the old YAML again as a new version.

## Consequences

- History is complete and cheap: a team publishes a few times a year.
- "Who changed the rules" is answered by `policies.created_by` and the audit
  log, without a separate history table.
- Two concurrent publishes for one team race on the unique index; the loser
  gets an error and retries. This has never happened in practice.
- Deleting a team's policy is impossible by design; a team that wants no
  rules publishes an explicit, minimal policy.
