# ADR 0002: Asset identity and provenance in the merge

- Status: Accepted
- Date: 2025-07-02
- Author: Aiko Tanaka
- Reviewers: Olivia Chen

## Context

The same asset reaches Atlas from several sources: `www.harborview-bank.example.test`
is in the zone file, in the certificate transparency feed and, through its
IP, in the port scan. Customers want one row per real thing, and they want
to know who told us about it and when ("why is this in my inventory?").
Sources disagree about details: the zone file says nothing about the
certificate, a cloud export names resources differently from how the
customer's DNS does.

## Decision

**Identity.** An asset is identified by `(org, kind, key)`; the key is
derived by `atlas.merge.identity.identity_key` from the observed value:

| Kind | Key |
|---|---|
| `domain`, `host` | normalized hostname (UTS 46, lower case, no trailing dot) |
| `ip` | canonical text form (IPv6 compressed, IPv4-mapped unwrapped) |
| `network` | canonical CIDR |
| `certificate` | SHA-256 of the DER, lower-case hex |
| `cloud_resource` | `nimbus:<account id>:<resource id>`, lower case |

Two observations with the same key are the same asset, whatever source they
came from.

**Provenance.** Every source that reported an asset gets one `AssetSource`
row, unique on `(asset, source_kind, source_name)`, with its own
`first_seen_at`, `last_seen_at` and the raw attributes of its last
observation. The asset's `first_seen_at` is the earliest of its sources,
`last_seen_at` the latest.

**Conflicting values.** The asset's `label` and `attributes` keep the values
of the **first source** that reported it. Later sources are recorded in
their `AssetSource.raw` but do not overwrite the asset. Rationale: the first
source is usually the customer's own (DNS, cloud export), and a noisy feed
should not be able to rename an asset that someone has already triaged.

**History.** Every difference the merge makes is an `AssetChange` row
(`created`, `updated` per field, `source_added`, `link_added`, ...) linked
to the import job. History is append-only.

## Consequences

- Provenance answers "who reported this" without a separate audit log.
- Identity is only as good as normalization: every importer must build keys
  through `identity_key`, or one real asset becomes two. When in doubt we
  prefer a duplicate to a wrong merge of two different assets, which is much
  harder to undo.
- Labels can be stale when the first source stops reporting; the source rows
  still show the latest values.
