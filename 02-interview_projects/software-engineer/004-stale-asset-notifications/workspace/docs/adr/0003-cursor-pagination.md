# ADR 0003: Cursor pagination for asset lists

- Status: Accepted (shipped in 0.9.0)
- Date: 2026-02-10
- Author: Daniel Mensah
- Reviewers: Olivia Chen, Rafael Souza

## Context

`GET /api/v1/assets/` used `limit`/`offset` with a `count`. Two problems
showed up once Quillstone passed 20k assets:

1. **Skipped and repeated rows.** The list is ordered by `last_seen_at`, and
   nightly imports bump `last_seen_at` on thousands of assets while a client
   is paging. An asset moved from page 40 to page 1 between two requests was
   never returned; others came back twice. Quillstone's CMDB sync reported
   "random" missing hosts.
2. **Cost.** `OFFSET 20000` makes Postgres read and discard 20,000 rows, and
   `count` is a full count of the filtered set on every page.

## Decision

Use DRF's `CursorPagination` for assets, asset changes and exposures:

- ordering `("-last_seen_at", "-id")` for assets: `id` breaks ties, which
  are common because one import stamps thousands of assets with the same
  `last_seen_at`;
- changes ordered `("-occurred_at", "-id")`, exposures `("-opened_at", "-id")`;
- `page_size` 50 by default, `page_size` query parameter up to 500;
- response `{"next", "previous", "results"}`; no `count`.

`offset` and `limit` are removed, not deprecated: keeping both would mean
two code paths and the bug above for every client that never migrates. The
0.9.0 release notes and a customer email announced the change four weeks
ahead.

The index `(org, last_seen_at)` serves the default ordering.

## Consequences

- Clients see each asset at most once per walk, and new assets appear at the
  front. An asset re-seen during a walk can still be missed by that walk; a
  full export should be filtered with `changed_since` and repeated.
- No total count in the API. Clients that need one filter and count on their
  side; the dashboard counts with its own query.
- Cursors are opaque and tied to the ordering. Changing the ordering is a
  breaking change for anyone holding a cursor.
- Jumping to page N is impossible. Nobody asked for it.
