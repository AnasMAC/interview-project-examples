# Changelog

Notable changes to Atlas. Dates are release dates (UTC). The public API is
`/api/v1/`; breaking changes to it are marked **Breaking**.

## 0.14.3 (2026-10-27)

- Fixed: a certificate naming the zone apex created a `host` next to the
  zone's `domain` of the same name; the merge now treats a hostname as one
  asset across both kinds (@atanaka).
- Fixed: `POST /api/v1/assets/` normalized keys with its own copy of the
  rules and could disagree with imports; it now uses the merge's
  `identity_key`. Archiving an asset resolves its open exposures at once
  (@dmensah).
- Added: `ATLAS_NOW` dev clock; compose starts the stack at the demo data's
  anchor (@ochen).
- Fixed: CT feed import counted a precertificate and its final certificate as
  two assets (@zpark, @atanaka).
- Fixed: webhook secrets passed in log `extra` fields were not masked (@dmensah).

## 0.14.2 (2026-10-13)

- Added: Nimbus inventory export v2 (`schema: nimbus.inventory/v2`), which
  Nimbus produces for accounts on its new account structure (@atanaka).
- Fixed: a webhook URL outside the allowed hosts was retried 8 times; it now
  goes `dead` at once with `blocked host` (@dmensah).

## 0.14.1 (2026-09-29)

- Fixed: hostnames with `ß` and other deviation characters were normalized
  with transitional IDNA rules; now UTS 46 non-transitional (@ochen).
- Changed: `ApiKey.last_used_at` is written at most once a minute per key
  (one UPDATE per request was a hot row for busy keys) (@ochen).

## 0.14.0 (2026-09-14)

- Changed: migrations squashed into a single `0001_initial` per app.
  Existing databases are faked forward; new migrations start at `0002_`
  (@ochen).
- Changed: Django 5.1, Django REST Framework 3.15, psycopg 3.2 (@ochen).
- Added: `seed --scale` and `scripts/bench.py` (@ochen).

## 0.13.0 (2026-08-11)

- Added: exposures overview page in the dashboard (@rsouza).
- Added: `owner_locked`: an owner set by hand is kept by ownership rules;
  `PATCH owner_team=""` releases it (@dmensah).

## 0.12.0 (2026-06-30)

- Changed: when sources disagree, an asset's label and attributes now come
  from the most recently seen source instead of the first one. Renamed cloud
  resources kept their launch-time names forever (@atanaka).
- Added: `include_archived` filter; archived assets seen again are restored
  (@atanaka, @dmensah).

## 0.11.0 (2026-05-19)

- Added: `changed_within=<hours>` filter and the "Changed in last 24h" link
  on the dashboard (@dmensah, @rsouza).
- Added: per-API-key rate limit, 600 requests per minute (@dmensah).

## 0.10.0 (2026-04-07)

- Added: `GET /api/v1/assets/{id}/changes/` (@dmensah).
- Added: `dangling_cname` exposure rule (@atanaka).
- Fixed: `cert_expiring` used the UTC date for "today"; it now uses the
  org's timezone (@atanaka).

## 0.9.0 (2026-02-24)

- **Breaking:** `/api/v1/assets/` uses cursor pagination (`next`,
  `previous`, `results`; `page_size` up to 500). `offset`, `limit` and
  `count` are gone. See ADR 0003 (@dmensah).
- Added: cursor pagination for exposures (@dmensah).

## 0.8.0 (2026-01-20)

- Added: saved views (personal in the dashboard, shared through the API) and
  CSV download of the current asset list (@rsouza, @dmensah).
- Added: `tag` ownership rules (@dmensah).

## 0.7.0 (2025-12-02)

- Added: certificate transparency feed importer, `certificate` assets with
  `covers` links to the hosts they name, `cert_expiring` rule (@zpark,
  @atanaka).

## 0.6.0 (2025-10-21)

- Added: exposure rules `unexpected_port` and `admin_panel_public`,
  evaluated after every import; per-org allowed ports (@atanaka).

## 0.5.0 (2025-09-16)

- Added: webhooks with HMAC-SHA256 signatures, delivered from an outbox with
  retries; `mockhook` for local development (@dmensah).

## 0.4.0 (2025-08-19)

- Added: ownership rules by hostname pattern and CIDR, evaluated by priority
  (@dmensah).

## 0.3.0 (2025-07-29)

- Added: port scan importer (Periscope JSON) and services on IP assets
  (@atanaka).

## 0.2.0 (2025-07-08)

- Added: Nimbus inventory importer (export v1), `cloud_resource` assets and
  per-source provenance (`AssetSource`), ADR 0002 (@atanaka).
- Added: Postgres job queue and `run_worker` (@ochen).

## 0.1.0 (2025-06-16)

- First release for the Harborview pilot: orgs and API keys, assets API,
  zone file importer, dashboard asset list with filters (@ochen, @dmensah,
  @rsouza).
