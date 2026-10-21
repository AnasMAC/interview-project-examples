# Policy DSL reference

Owner: Tobias Krüger. Last reviewed for 3.1.

A team's policy is a YAML document stored as a new **version** every time it
is published (`POST /v1/policies` or `python -m gatekeeper.cli import-policy`).
The highest version is the active policy; older versions stay readable at
`GET /v1/policies/<version>` and are never changed (ADR 0002).

## Shape

```yaml
policy: 1                 # DSL version, required; 1 is the only version
rules:                    # required, non-empty, evaluated in this order
  - id: dependency.max_severity
    max: high
    action: block         # block (default) or warn
    when:                 # optional, see "Conditions"
      environments: [production]
```

Each rule appears at most once. A violated rule produces its `action`; a rule
that holds produces `pass`. The decision is `block` if any result is `block`,
otherwise `warn` if any is `warn`, otherwise `pass`. A team without a policy
gets a single `policy.missing` warning, so publish one before switching your
pipeline to "fail on block".

## Rules

| id | parameter | violated when | evidence |
|---|---|---|---|
| `dependency.max_severity` | `max` (required): `none`, `low`, `medium`, `high`, `critical` | a package has a vulnerability **above** `max` (`max: high` passes a high and blocks a critical) | `dependencies` |
| `secrets.allowed` | `max` (default 0) | more than `max` secret findings | `secrets` |
| `sast.max_high` | `max` (default 0) | more than `max` **new** high + critical SAST findings (findings already on the default branch do not count) | `sast` |
| `tests.min_pass_rate` | `min` (required, 0 to 1) | `passed / (passed + failed)` is below `min`; skipped tests are left out; no executed tests at all fails unless `min: 0` | `tests` |
| `signing.required` | none | the release artifact is not signed, or the signature does not verify | `signing` |

When the pipeline did not send the evidence a rule needs, the rule produces
its `action` with `details.missing: true`. The legacy runner sends a secret
*count* only, and no SAST totals; both are enough for these rules.

`max` and `min` must be YAML numbers (or a severity name for
`dependency.max_severity`): `max: "0"` and `max: true` are errors.

## Conditions

`when` restricts a rule to some builds. Both keys are optional lists; when
both are given, both must match.

```yaml
when:
  branches: ["main", "release/*"]   # fnmatch globs on the branch name
  environments: [production, staging]
```

- Branch names are what the CI adapter produced: `refs/heads/` is already
  stripped, and a tag build (`refs/tags/v4.12.0`) has the tag as its branch.
  Matching is case-sensitive and `*` also matches `/`, so `release/*`
  matches `release/4.12/hotfix-1` too.
- Environments are `production`, `staging` and `development`.
- A rule whose `when` does not match is skipped: it produces no result at
  all, not a `pass`.
- An empty list (`branches: []`) is an error rather than "never".

## Validation

Validation is strict and reports every problem at once as 422
`invalid_policy`:

```json
{"error": {"code": "invalid_policy",
  "message": "policy is invalid: rules[1].max must be a whole number >= 0 (and 1 more)",
  "details": {"errors": [
    {"path": "rules[1].max", "message": "must be a whole number >= 0"},
    {"path": "rules[3]", "message": "unknown key 'treshold'"}]}}}
```

Errors include unknown keys anywhere, duplicate mapping keys, duplicate
rules, unknown rule ids, wrong types and documents over 64 KiB. Try a draft
before publishing it with the dry run, which evaluates sample evidence
against your draft and current waivers and stores nothing:

```sh
curl -s -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d @dry-run.json http://127.0.0.1:8090/v1/policies/dry-run
```

## A complete example

The Payments API policy (shortened):

```yaml
policy: 1
rules:
  - {id: dependency.max_severity, max: high, action: block}
  - {id: secrets.allowed, max: 0, action: block}
  - {id: sast.max_high, max: 0, action: warn}
  - {id: tests.min_pass_rate, min: 0.98, action: block}
  - id: signing.required
    action: block
    when: {branches: [main, "release/*"], environments: [production]}
```

## Waivers and rules

A waiver names one rule id, optionally one service and a version range
(`>=4.12.0,<4.13.0`). A covered violation is reported as `warn` with
`waiver_id` set and its message prefixed `waived: `; it never becomes a
`pass`. See `docs/api.md` for requesting waivers.
