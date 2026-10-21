# CS-0412: Harborview sees every cloud resource twice

| | |
|---|---|
| From | Omar Haddad (customer success) |
| Date | 2026-10-30 |
| Customer | Harborview Bank (`harborview-bank`) |
| Priority | High; their CISO is asking whether the inventory can be trusted |
| Status | Needs investigation |

## Customer report

> Since around 20 October every one of our Nimbus resources appears twice in
> Atlas. One copy keeps our tags and owner but has not been "seen" since the
> 18th; the other is new, has no tags, and is owned by nobody. Our SIEM got a
> burst of `asset.created` webhooks on the 19th for things that have existed
> for two years. Our Nimbus admins say nothing changed except that we moved
> to Nimbus's new account structure on the 19th: same resources, same
> resource ids.
> -- Harborview cloud platform team

## What I know

- The migration on Nimbus's side happened 2026-10-19 02:00 UTC. Their nightly
  export has looked different since then.
- Samples from before and after are in `fixtures/imports/nimbus/`:
  `harborview-bank-2026-09-30.v1.json` and
  `harborview-bank-2026-10-28.v2.json`. Same resources, as far as I can
  tell.
- In the demo data (`make seed`) the Harborview cloud resources show the same
  pattern, if you want to look at it in the dashboard.
- Orchid Grid also exports Nimbus v2 (`orchid-grid-2026-11-03.v2.json`) and
  has not complained, but they joined Nimbus after the new structure existed.
- Quillstone is on the old export and will be migrated by Nimbus "in Q1".

## Asks from me

1. Why does this happen? I need a short explanation I can send to the
   customer (no internals they would not understand).
2. Stop it from happening on the next import, for Harborview and for
   Quillstone when their turn comes.
3. Fix the data they already have: one asset per resource again, keeping
   the history, tags, owner and any open exposures of the old copy. They
   would rather not receive another burst of webhooks while we clean up.
4. Tell me whether anything else could have been affected (webhooks sent,
   exposures opened twice, ownership).

## Not in scope

Changing how Nimbus exports work, or asking the customer to rename anything
on their side.
