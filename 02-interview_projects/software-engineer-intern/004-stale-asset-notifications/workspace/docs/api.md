# Atlas API v1

Owner: Daniel Mensah. Base URL `/api/v1/`. JSON in, JSON out. Field-level
details live in `atlas/api/serializers.py`; this page is the contract we give
customers.

## Authentication

Every request carries an org API key:

```
Authorization: Bearer atl_DEMO_k5lv9z8g76x8az3c8x0ajrk98pwkji8f
```

A key belongs to exactly one org and sees only that org's data. A missing,
malformed, unknown or revoked key answers `401 unauthenticated`. Another
org's object answers `404 not_found`, never `403`, so ids cannot be probed.
Keys are created by Brindlecove staff (see `docs/runbook.md`); the raw value
is shown once and only its SHA-256 is stored. The demo keys of the three
seeded orgs are in `docs/architecture.md` §9.

## Rate limits

600 requests per minute per API key (`ATLAS_API_RATE`). Over the limit:
`429 throttled` with a `Retry-After` header and
`details.retry_after_seconds`.

## Errors

```json
{"error": {"code": "validation_failed", "message": "Invalid input.",
           "details": {"changed_since": ["Include a UTC offset, e.g. 2026-11-04T00:00:00Z."]}}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `validation_failed` | bad field or filter; `details` maps the name to messages |
| 400 | `parse_error` | body is not valid JSON |
| 401 | `unauthenticated` | see Authentication |
| 404 | `not_found` | missing, or another org's object |
| 405 | `method_not_allowed` | e.g. `PUT` (use `PATCH`) |
| 409 | `conflict` | duplicate asset, tag or saved-view name |
| 429 | `throttled` | see Rate limits |

## Pagination

Lists of assets, changes and exposures use cursor pagination (since 0.9,
ADR 0003):

```json
{"next": "https://atlas.brindlecove.example.test/api/v1/assets/?cursor=cD0yMDI2LTExLTA1...",
 "previous": null,
 "results": [...]}
```

Follow `next` until it is `null`. `page_size` defaults to 50, maximum 500.
There is no total count. Assets are ordered by `last_seen_at` descending,
then `id` descending; changes by `occurred_at`, exposures by `opened_at`
(both descending, then `id`). Tags, ownership rules, webhooks and saved views
are small and come back as plain arrays.

## Assets

`GET /api/v1/assets/` lists the org's assets. Filters (combine freely):

| Parameter | Meaning |
|---|---|
| `kind` | `domain`, `host`, `ip`, `network`, `certificate`, `cloud_resource`; repeat for any of several |
| `tag` | tag name; repeat to require **all** of them |
| `owner` | team name, or `-` for assets without an owner |
| `exposure` | a rule name, or `any`: assets with an open exposure |
| `changed_since` | ISO 8601 with offset (`2026-11-04T00:00:00-05:00`); naive times are rejected |
| `changed_within` | hours, e.g. `24`: assets with a change in the last N elapsed hours |
| `q` | case-insensitive substring of `key` or `label` |
| `include_archived` | `1` to include archived assets (hidden by default) |

```sh
curl -H "Authorization: Bearer $ATLAS_KEY" \
  "https://atlas.brindlecove.example.test/api/v1/assets/?kind=host&exposure=any&tag=pci"
```

An asset:

```json
{"id": 1187, "kind": "host", "key": "api-stg-03.payments.harborview-bank.example.test",
 "label": "api-stg-03.payments.harborview-bank.example.test",
 "owner_team": "payments-platform", "owner_locked": false, "tags": ["pci", "staging"],
 "attributes": {"zone": "harborview-bank.example.test"},
 "first_seen_at": "2026-09-11T07:15:00Z", "last_seen_at": "2026-11-05T08:15:00Z",
 "archived_at": null, "open_exposures": 1}
```

`key` is the identity within the org and kind: a normalized hostname (IDN in
punycode, lower case, no trailing dot), an IP in canonical text form, a CIDR,
a certificate's SHA-256 fingerprint, or `nimbus:<account id>:<resource id>`.
`label` is display text from the most recent source and may contain any
characters; escape it when you render it.

`attributes` by kind: `ip`/`network` `{"version"}`; `certificate`
`{"subject_cn", "sans", "issuer", "serial", "not_before", "not_after"}`;
`cloud_resource` `{"provider", "account_id", "resource_type", "region",
"public_ip"}`; `host`/`domain` `{"zone"}` when known.

### Example: export every host

To page through all hosts of an org, 50 at a time:

```sh
curl -H "Authorization: Bearer $ATLAS_KEY" \
  "https://atlas.brindlecove.example.test/api/v1/assets/?kind=host&offset=100&limit=50"
```

```json
{"count": 4512,
 "next": "https://atlas.brindlecove.example.test/api/v1/assets/?kind=host&limit=50&offset=150",
 "previous": "https://atlas.brindlecove.example.test/api/v1/assets/?kind=host&limit=50&offset=50",
 "results": [...]}
```

### Create, update, archive

`POST /api/v1/assets/` with `{"kind", "key", "label"?, "tags"?}` adds an
asset by hand. `key` is normalized first (`WWW.Example.TEST.` becomes
`www.example.test`); if the normalized key already exists for that kind the
answer is `409 conflict` (a `host` and a `domain` with the same name are the
same asset). Keys are normalized exactly as imports do, so an asset you add
and one an import finds later are one asset with two sources. The asset gets an `api` source named after the API key
(`api key <name>`) and ownership rules are applied. Answers `201` with the
detail body.

`GET /api/v1/assets/{id}/` adds `sources` (`source_kind, source_name,
first_seen_at, last_seen_at`), `links` (`relation, direction, asset {id,
kind, key}, source_kind, first_seen_at, last_seen_at`), `services` (`port,
protocol, service, product, banner, first_seen_at, last_seen_at, closed_at`)
and `exposures`.

`PATCH /api/v1/assets/{id}/` accepts any of:

- `label`: replaces the display label (the next import may set it again);
- `owner_team`: sets the owner and locks it, so ownership rules leave the
  asset alone; `""` removes the lock and lets the rules decide again;
- `tags`: the complete list of tag names; missing tags are created.

`DELETE /api/v1/assets/{id}/` archives the asset (`204`). Archived assets
keep their history and come back if an import sees them again.

### History

`GET /api/v1/assets/{id}/changes/`: the asset's append-only history, newest
first, cursor-paginated.

```json
{"id": 90311, "kind": "service_opened", "field": "8443/tcp", "old_value": null,
 "new_value": {"service": "https", "product": "Jenkins"}, "source_kind": "port_scan",
 "job": 412, "occurred_at": "2026-11-01T09:30:12Z"}
```

Kinds: `created`, `updated` (`field` = `label`, `attributes`,
`archived_at`, or `kind` when a host turned out to be the zone's domain), `source_added`, `link_added` (`field` = relation, new value =
target key), `service_opened`, `service_closed`, `owner_changed`, `tagged`,
`untagged`, `exposure_opened`, `exposure_resolved` (`field` = rule, new value
= `{"exposure_id", "subject", "severity"}`), `archived`.

## Tags

`GET /api/v1/tags/` (with `asset_count`), `POST {"name", "description"?}`
(names are slugs; duplicates `409`), `DELETE /api/v1/tags/{name}/` removes
the tag from every asset, recording `untagged` changes.

## Ownership rules

`GET/POST /api/v1/ownership-rules/`, `PATCH/DELETE
/api/v1/ownership-rules/{id}/`. A rule is `{"pattern_type", "pattern",
"team", "priority", "enabled"}`:

| `pattern_type` | Matches |
|---|---|
| `hostname` | `host` and `domain` assets whose key matches a glob; `*` also matches dots, so `*.harborview-bank.example.test` covers `a.b.harborview-bank.example.test` |
| `cidr` | `ip` assets inside the network, and `network` assets contained in it |
| `tag` | assets carrying the tag |

Enabled rules are tried by `priority` (lower first), ties by age; the first
match sets `owner_team`; no match clears it. Assets with a locked owner are
skipped. Rules run after every import and on `POST
/api/v1/ownership-rules/apply/`, which re-applies all of them and answers
`{"changed": <count>}`.

## Exposures

`GET /api/v1/exposures/`, read-only. Filters `status` (`open`,
`resolved`), `rule`, `severity`, `asset` (id).

| Rule | Fires when | Severity |
|---|---|---|
| `admin_panel_public` | a public IP serves something that looks like an admin UI | high |
| `cert_expiring` | a certificate expires within the org's warning period (30 days), counted in the org's timezone | medium, critical once expired |
| `dangling_cname` | a host is a CNAME to a host that does not resolve | high |
| `unexpected_port` | a public IP has an open port outside the org's allowed ports | medium |

An exposure is `{"id", "asset", "rule", "subject", "severity", "status",
"title", "details", "opened_at", "last_evaluated_at", "resolved_at"}`.
`subject` says what triggered it (`"8443/tcp"`, the CNAME target, or `""`).
Exposures resolve themselves when the condition disappears or the asset is
archived.

## Webhooks

`GET/POST /api/v1/webhooks/`, `PATCH/DELETE /api/v1/webhooks/{id}/`. Body
`{"name", "url", "events", "enabled"?, "secret"?}`. `events` is any of
`asset.created`, `asset.changed`, `exposure.opened`, `exposure.resolved`,
`import.completed`. Omit `secret` and Atlas generates one; it is returned
once in the `201` response and never again. URLs must be http(s) and pass
the host allow-list.

Each delivery is a `POST` with `Content-Type: application/json`,
`X-Atlas-Event`, `X-Atlas-Delivery` and

```
X-Atlas-Signature: t=1793889000,v1=5f2c...e9
```

where `v1` is the hex HMAC-SHA256 of `"<t>." + raw body` with the webhook
secret. Verify against the raw bytes, compare in constant time and reject
timestamps older than five minutes. Non-2xx answers are retried with
backoff (30 s doubling, at most 1 h apart) and given up after 8 attempts.

```json
{"id": "evt_8812", "event": "exposure.opened", "org": "harborview-bank",
 "occurred_at": "2026-11-05T14:30:00Z",
 "data": {"asset": {"id": 1187, "kind": "ip", "key": "198.51.100.20", "label": "198.51.100.20",
                    "owner_team": "network-engineering"},
          "exposure": {"id": 77, "rule": "unexpected_port", "subject": "8080/tcp",
                       "severity": "medium", "title": "Unexpected open port 8080/tcp on 198.51.100.20",
                       "opened_at": "2026-11-05T14:30:00Z", "resolved_at": null}}}
```

## Saved views

`GET/POST /api/v1/saved-views/`, `GET/DELETE /api/v1/saved-views/{id}/`.
`{"name", "querystring"}` where `querystring` uses the asset filters above
(`kind=host&owner=-`). Atlas stores it in canonical form (known parameters
only, sorted) and rejects invalid filters with `400`. Views created through
the API are shared with the whole org and show up in the dashboard; a second
shared view with the same name is a `409`.
