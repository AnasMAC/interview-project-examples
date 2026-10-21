# REQ-0214: Tell owners when their assets go stale

| | |
|---|---|
| From | Freya Lindqvist (product) |
| Date | 2026-10-26 |
| Customers | Harborview Bank, Orchid Grid (asked separately) |
| Priority | High; Harborview's Q4 audit asks for evidence of "inventory hygiene" |
| Status | Ready for design |

## Problem

An asset that no source has reported for weeks is either decommissioned
(and should be archived) or has fallen out of our view (and is the scary
kind of exposure: still live, no longer scanned). Today nobody notices
either. Harborview's security lead found 40 hosts last seen in September by
sorting the CSV export by hand.

## What we want

- Each org decides when an asset counts as **stale**: no source has seen it
  for N days. Default 14, Harborview wants 7, Orchid 30 (their field
  equipment reports rarely).
- When an asset becomes stale, its **owner team is told once**, through the
  org's webhooks (a new event, e.g. `asset.stale`, with the asset and the
  owner), not on every evaluation. Unowned assets are reported too, with an
  empty owner, so someone picks them up.
- If the asset is seen again it stops being stale, and becoming stale again
  later notifies again.
- The API can list stale assets (a filter on `GET /api/v1/assets/`), and the
  dashboard shows a "stale" badge on the list and detail pages with "last
  seen 18 days ago".
- Archived assets are never stale.

## Notes

- "Days" are calendar days in the org's timezone, as customers think of them
  ("not seen since Monday"), but please say in the PR what you chose and why.
- Notifications must not fire for every stale asset on the day we ship: the
  seeded orgs already have a few hundred. A one-off "N assets are stale" event
  per org, or a quiet first run, would both be fine; propose one.
- Harborview's Nimbus duplicates (CS-0412) will show up as stale cloud
  resources. That is expected and not this ticket's problem, but the
  notification should make it easy to tell why an asset is stale (which
  sources, last seen when).

## Done when

- The threshold is configurable per org (migration), the check runs in the
  worker, notifications go out once per stale period, and the API filter and
  the dashboard badge exist.
- Tests cover the boundary (exactly N days), re-seen assets and archived
  assets.

## Comments

**Olivia Chen (CTO), 2026-10-28.** The design inside Atlas is up to whoever
picks this up. These are the fixed points, so Daniel and Rafael can review
it and we can write integration tests against it before the Harborview demo:

- `Org.stale_after_days`: positive integer, default 14, added by a
  migration. Harborview 7 and Orchid 30 must be in effect wherever those
  orgs exist: existing databases, and the demo data Freya shows from a fresh
  `make setup`.
- The day rule: an asset is stale when the org-local calendar date of its
  `last_seen_at` is `stale_after_days` or more days before the org-local
  date of now (`Org.timezone`). Exactly N days is stale, N-1 is not.
  Calendar dates, not 24-hour periods.
- `last_seen_at` is the input: the newest sighting by any source. Not
  `updated_at` (it moves on every write, including a label edit through
  the API) and not the change history.
- Archived assets are never stale and never notified.
- `asset.stale` is a normal webhook event: customers subscribe to it
  through the webhooks API like the other events, and only the org's
  enabled webhooks that subscribed get it, signed and retried like the
  rest. `data` carries at least `{"asset": {"id", "kind", "key", "label"},
  "owner_team", "last_seen_at", "stale_since" or "days_since_seen",
  "sources": [{"kind", "name", "last_seen_at"}]}`; `owner_team` is `""`
  for unowned assets.
- Once per stale period: running the check again does not repeat the
  event. An asset seen again is fresh; if it goes stale again later, that
  is a new event.
- The check exists as job kind `stale.check` (`enqueue(org, "stale.check",
  {})` checks that org) and as a management command `check_stale_assets
  [--org SLUG]` that runs it right away for one org or all of them. Ops
  will put the command in cron every hour, so it must be safe to run as
  often as anyone likes.
- First run: the first check for an org must not send one event per asset
  that is already stale. Quiet, or one summary event per org; pick one and
  write down why. After that, one `asset.stale` per asset as it goes stale.
- API: `GET /api/v1/assets/?stale=true`, as one of the shared filters in
  `atlas/assets/filters.py`, so the dashboard and saved views can use it.
- Delivery is the org's webhooks and nothing else. The receiving side
  (their SIEM or ticketing) routes on `owner_team`; we are not adding
  e-mail or chat to Atlas for this.

**Freya Lindqvist (product), 2026-11-04.** Thanks Olivia. Two questions
from my call with Harborview's security lead, for whoever builds this:
she asked whether each owner team (payments-platform, digital-banking and
so on) will get its own e-mail when one of their assets goes stale. I said
I would check what we can promise for the demo. She also asked how many of
their assets are stale today; I have been saying "a few hundred", and I
would like a real number for Harborview and for Orchid.
